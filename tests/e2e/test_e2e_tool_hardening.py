"""Real-browser regressions for tool identity, recovery and storage semantics."""

import asyncio
import re
import socket
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anyio
import anyio.lowlevel
import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from typing_extensions import override

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager
from justpen_browser_mcp.tools import register_all
from justpen_browser_mcp.tools.cookies import _storage_in_origin

from .conftest import call

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox._warnings.LeakWarning"),
]

# Direct navigation/content calls prepare evidence; tool deadlines stay separate.
SETUP_TIMEOUT_MS = 30_000


@pytest.fixture
async def hardening_browser():
    manager = InstanceManager(BrowserServerConfig(operation_timeout_seconds=5))
    server = FastMCP("hardening-e2e")
    register_all(server, manager)
    try:
        await manager.create("review", humanize=False, firefox_user_prefs={"dom.disable_open_during_load": False})
        page = await manager.active_page("review")
        page.set_default_timeout(500)
        async with Client(server) as client:
            yield manager, page, client
    finally:
        await manager.shutdown_all()


@pytest.fixture
def download_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/file")
                self.end_headers()
                return
            if self.path == "/other-origin":
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{server.server_port}/child")
                self.end_headers()
                return
            body = b"evidence" if self.path == "/file" else b"<!doctype html><title>child</title>"
            if self.path == "/popup":
                body = b"<!doctype html><title>requested</title><script>window.open('/child')</script>"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream" if self.path == "/file" else "text/html")
            self.send_header("Content-Length", str(len(body)))
            if self.path == "/file":
                self.send_header("Content-Disposition", 'attachment; filename="evidence.txt"')
            self.end_headers()
            self.wfile.write(body)

        @override
        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


async def test_download_filename_does_not_turn_failure_into_success(hardening_browser):
    _, _, client = hardening_browser
    with closing(socket.socket()) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    result = await call(client, "browser_navigate", {"instance": "review", "url": f"http://127.0.0.1:{port}/download"})
    assert result["error_type"] == "navigation_failed"


async def test_download_event_after_redirect_is_success(hardening_browser, download_site):
    _, _, client = hardening_browser
    result = await call(client, "browser_navigate", {"instance": "review", "url": f"{download_site}/redirect"})
    assert result["status"] == "success", result
    assert result["data"]["download"] is True


async def test_duplicate_text_visibility_and_disappearance(hardening_browser):
    _, page, client = hardening_browser
    await page.set_content(
        '<section aria-label="Items"><span hidden>Done</span><span>Done</span></section>', timeout=SETUP_TIMEOUT_MS
    )
    for name, arguments in [
        ("browser_wait_for", {"text": "Done"}),
        ("browser_verify_text_visible", {"text": "Done"}),
    ]:
        result = await call(client, name, {"instance": "review", **arguments})
        assert result["status"] == "success", result
    snapshot = await call(client, "browser_snapshot", {"instance": "review"})
    region = next(line for line in snapshot["data"]["snapshot"].splitlines() if 'region "Items"' in line)
    match = re.search(r"\[ref=(\w+)\]", region)
    assert match is not None
    ref = match.group(1)
    verified = await call(
        client, "browser_verify_list_visible", {"instance": "review", "container_ref": ref, "items": ["Done"]}
    )
    assert verified["status"] == "success", verified
    visible = await call(client, "browser_wait_for", {"instance": "review", "text_gone": "Done"})
    assert visible["error_type"] == "wait_timeout"
    await page.locator("span").last.evaluate("el => el.hidden = true", timeout=SETUP_TIMEOUT_MS)
    hidden = await call(client, "browser_wait_for", {"instance": "review", "text_gone": "Done"})
    assert hidden["status"] == "success", hidden


async def test_storage_dump_preserves_proto_key(hardening_browser, test_site):
    _, page, client = hardening_browser
    await page.goto(test_site, timeout=SETUP_TIMEOUT_MS)
    await page.evaluate("() => {localStorage.clear(); localStorage.setItem('__proto__', 'evidence');}")
    result = await call(client, "browser_get_local_storage", {"instance": "review", "origin": test_site})
    assert result["data"]["items"] == {"__proto__": "evidence"}
    written = await call(
        client,
        "browser_set_local_storage",
        {"instance": "review", "origin": test_site, "items": {"__proto__": "updated"}},
    )
    assert written["status"] == "success", written
    assert await page.evaluate("localStorage.getItem('__proto__')") == "updated"


@pytest.mark.parametrize(
    ("requested", "canonical"),
    [
        ("http://bücher.localhost", "http://xn--bcher-kva.localhost"),
        ("http://[0:0:0:0:0:0:0:1]", "http://[::1]"),
        ("http://localhost:80", "http://localhost"),
        ("https://localhost:443", "https://localhost"),
    ],
)
async def test_storage_uses_browser_origin_canonicalization(hardening_browser, requested, canonical):
    _, page, client = hardening_browser
    # All navigations are fulfilled in-process, without DNS or network access.
    await page.context.route("**/*", lambda route: route.fulfill(body="<html>local</html>", content_type="text/html"))
    result = await call(
        client, "browser_set_local_storage", {"instance": "review", "origin": requested, "items": {"key": "value"}}
    )
    assert result["status"] == "success", result
    read = await call(client, "browser_get_local_storage", {"instance": "review", "origin": canonical, "key": "key"})
    assert read["data"]["value"] == "value"


async def test_storage_accepts_browser_canonical_ipv4_origin(hardening_browser, test_site):
    _, _, client = hardening_browser
    origin = test_site.replace("127.0.0.1", "127.1")
    written = await call(
        client, "browser_set_local_storage", {"instance": "review", "origin": origin, "items": {"key": "value"}}
    )
    assert written["status"] == "success", written
    read = await call(client, "browser_get_local_storage", {"instance": "review", "origin": test_site, "key": "key"})
    assert read["data"]["value"] == "value"


async def test_storage_rejects_cross_origin_redirect_before_write(hardening_browser, download_site):
    _, page, client = hardening_browser
    result = await call(
        client,
        "browser_set_local_storage",
        {"instance": "review", "origin": f"{download_site}/other-origin", "items": {"secret": "value"}},
    )
    assert result["error_type"] == "invalid_params", result
    await page.goto(download_site.replace("127.0.0.1", "localhost") + "/child", timeout=SETUP_TIMEOUT_MS)
    assert await page.evaluate("localStorage.getItem('secret')") is None


async def test_generated_locator_preserves_nth_semantics(hardening_browser):
    _, page, client = hardening_browser
    await page.set_content("<button>Same</button><button>Same</button>", timeout=SETUP_TIMEOUT_MS)
    snapshot = await call(client, "browser_snapshot", {"instance": "review"})
    line = next(line for line in snapshot["data"]["snapshot"].splitlines() if 'button "Same"' in line)
    match = re.search(r"\[ref=(\w+)\]", line)
    assert match is not None
    ref = match.group(1)
    generated = await call(client, "browser_generate_locator", {"instance": "review", "ref": ref})
    data = generated["data"]
    count = await call(
        client, "browser_run_code", {"instance": "review", "code": f"return await page.{data['python_syntax']}.count()"}
    )
    assert await page.locator(data["internal_selector"]).count() == count["data"]["result"] == 1


async def test_new_tab_popup_and_stable_id(hardening_browser, download_site):
    manager, original, client = hardening_browser
    await original.set_content(
        f'<a href="{download_site}/child" target="_blank">Open popup</a>', timeout=SETUP_TIMEOUT_MS
    )

    async def open_popup_during_navigation(route):
        async with original.context.expect_page() as popup:
            await original.get_by_role("link", name="Open popup").click()
        await popup.value
        await route.fulfill(body="<!doctype html><title>requested</title>", content_type="text/html")

    await original.context.route(f"{download_site}/popup", open_popup_during_navigation)
    created = await call(
        client, "browser_tabs", {"instance": "review", "action": "new", "url": f"{download_site}/popup"}
    )
    assert created["status"] == "success", created
    assert len(original.context.pages) == 3
    selected = await manager.active_page("review")
    assert selected.url == f"{download_site}/popup"
    page_id = created["data"]["page_id"]
    await original.close()
    selected_again = await call(client, "browser_tabs", {"instance": "review", "action": "select", "page_id": page_id})
    assert selected_again["status"] == "success", selected_again
    assert await manager.active_page("review") is selected
    closed = await call(client, "browser_tabs", {"instance": "review", "action": "close", "page_id": page_id})
    assert closed["status"] == "success", closed
    assert selected.is_closed()


async def test_dialog_recovery_unblocks_pending_evaluation(hardening_browser):
    manager, page, client = hardening_browser
    dialog_seen = asyncio.Event()
    page.on("dialog", lambda _dialog: dialog_seen.set())
    evaluation = asyncio.create_task(
        call(
            client,
            "browser_evaluate",
            {"instance": "review", "page_id": manager.page_id("review", page), "expression": "alert('recover me')"},
        )
    )
    try:
        await asyncio.wait_for(dialog_seen.wait(), timeout=2)
        recovered = await asyncio.wait_for(
            call(
                client,
                "browser_handle_dialog",
                {"instance": "review", "page_id": manager.page_id("review", page), "accept": False},
            ),
            timeout=2,
        )
        assert recovered["status"] == "success", recovered
        result = await asyncio.wait_for(evaluation, timeout=2)
        assert result["status"] == "success", result
        assert manager.get_modal_states("review") == []
    finally:
        if not evaluation.done():
            evaluation.cancel()
        await asyncio.gather(evaluation, return_exceptions=True)


async def test_explicit_data_navigation(hardening_browser):
    _, _, client = hardening_browser
    result = await call(client, "browser_navigate", {"instance": "review", "url": "data:text/html,<title>a.b</title>"})
    assert result["status"] == "success", result
    assert result["data"]["title"] == "a.b"


@pytest.mark.parametrize("accept", [True, False])
async def test_already_handled_native_dialog_does_not_block_instance(hardening_browser, accept):
    manager, page, client = hardening_browser
    seen = asyncio.Event()
    page.on("dialog", lambda _dialog: seen.set())
    evaluation = asyncio.create_task(page.evaluate("alert('handled elsewhere')"))
    try:
        await asyncio.wait_for(seen.wait(), timeout=2)
        modal = manager.get_modal_states("review")[0]["object"]
        await modal.dismiss()
        await asyncio.wait_for(evaluation, timeout=2)
        result = await call(client, "browser_handle_dialog", {"instance": "review", "accept": accept})
        assert result["status"] == "error", result
        assert "already handled" in result["message"]
        assert result["operation"]["outcome"] == "unknown"
        assert manager.get_modal_states("review") == []
        following = await call(client, "browser_evaluate", {"instance": "review", "expression": "2 + 2"})
        assert following["data"]["result"] == 4
    finally:
        if not evaluation.done():
            evaluation.cancel()
        await asyncio.gather(evaluation, return_exceptions=True)


async def test_cancelled_storage_operation_closes_real_temporary_page(hardening_browser, test_site, monkeypatch):
    manager, active, _ = hardening_browser
    context = active.context
    create_page = context.new_page
    created = []
    with anyio.CancelScope() as scope:

        async def cancel_navigation(*_args, **_kwargs):
            scope.cancel()
            await anyio.lowlevel.checkpoint()

        async def create_then_cancel():
            page = await create_page()
            created.append(page)
            # Cancel at an explicit checkpoint before sending a navigation,
            # then require cleanup to close this real browser page.
            monkeypatch.setattr(page, "goto", cancel_navigation)
            return page

        monkeypatch.setattr(context, "new_page", create_then_cancel)
        await _storage_in_origin(context, test_site, "get", mgr=manager, instance="review")
    assert len(created) == 1
    assert created[0].is_closed()
    assert context.pages == [active]
