"""Verify metadata on the wire, including the first-popup timing limitation."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from anyio import Path as AsyncPath
from typing_extensions import override

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox._warnings.LeakWarning"),
]

PREFIX = "justpen-browser-metadata-"


@pytest.fixture
def metadata_site():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self._respond()

        def do_POST(self):
            self._respond()

        def _respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append((self.path, {key.lower(): value for key, value in self.headers.items()}, body))
            if self.path.startswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{server.server_port}/final")
                self.end_headers()
                return
            response = (
                b'<html><body><iframe src="/frame"></iframe>'
                b'<script src="/script"></script><form method="post" action="/submit">'
                b'<input name="value" value="untouched"></form></body></html>'
                if self.path == "/main"
                else b"<html><body>ready</body></html>"
            )
            if self.path == "/script":
                response = b"window.metadataFixtureReady = true;"
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if self.path == "/script" else "text/html")
            self.send_header("Content-Length", str(len(response)))
            if self.path == "/cache":
                self.send_header("Cache-Control", "max-age=120")
            self.end_headers()
            self.wfile.write(response)

        @override
        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def metadata(headers):
    return {key: value for key, value in headers.items() if key.startswith(PREFIX)}


async def test_navigation_frames_subresources_fetch_forms_and_two_pages(metadata_site, pinned_browser_runtime):
    site, requests = metadata_site
    manager = InstanceManager(BrowserServerConfig(), browser_runtime=pinned_browser_runtime)
    try:
        record = await manager.create("wire")
        first = await manager.target_page("wire")
        first_id = manager.page_id("wire", first)
        await first.goto(f"{site}/main")
        await first.evaluate("fetch('/fetch', {method: 'POST', body: 'original-body'})")
        async with first.expect_navigation():
            await first.locator("form").evaluate("form => form.submit()")
        second = await record.context.new_page()
        second_id = manager.page_id("wire", second)
        await manager.target_page("wire", second_id)
        await second.goto(f"{site}/second")
        manager.set_active_page("wire", 1)
        await asyncio.gather(first.goto(f"{site}/first-again"), second.goto(f"{site}/redirect"))
        by_path = {path: (headers, body) for path, headers, body in requests}
        for path in (
            "/main",
            "/frame",
            "/script",
            "/fetch",
            "/submit",
            "/first-again",
            "/second",
            "/redirect",
            "/final",
        ):
            headers, _body = by_path[path]
            assert metadata(headers) == {
                f"{PREFIX}instance-name": "wire",
                f"{PREFIX}instance-id": record.instance_id,
                f"{PREFIX}page-id": second_id if path in {"/second", "/redirect", "/final"} else first_id,
            }
        assert by_path["/fetch"][1] == b"original-body"
        assert by_path["/submit"][1] == b"value=untouched"
        assert first_id != second_id
    finally:
        await manager.shutdown_all()


async def test_first_popup_request_is_instance_tagged_then_page_setup_completes(
    metadata_site, pinned_browser_runtime, tmp_path
):
    site, requests = metadata_site
    manager = InstanceManager(BrowserServerConfig(), browser_runtime=pinned_browser_runtime)
    try:
        record = await manager.create("popup")
        opener = await manager.target_page("popup")
        await opener.goto(f"{site}/opener")
        async with opener.expect_popup() as opened:
            await opener.evaluate("url => window.open(url)", f"{site}/popup-first")
        popup = await opened.value
        popup_id = manager.page_id("popup", popup)
        await manager.target_page("popup", popup_id)
        await popup.goto(f"{site}/popup-ready")
        by_path = {path: headers for path, headers, _body in requests}
        first = metadata(by_path["/popup-first"])
        assert first[f"{PREFIX}instance-id"] == record.instance_id
        # Page is exposed after its first request. Never substitute the opener ID.
        assert first.get(f"{PREFIX}page-id") in (None, popup_id)
        assert metadata(by_path["/popup-ready"]) == {
            f"{PREFIX}instance-name": "popup",
            f"{PREFIX}instance-id": record.instance_id,
            f"{PREFIX}page-id": popup_id,
        }
        await AsyncPath(tmp_path / "popup-wire-evidence.json").write_text(
            json.dumps({"first_request": first, "popup_page_id": popup_id})
        )
    finally:
        await manager.shutdown_all()


@pytest.mark.parametrize("enabled", [True, False])
async def test_persistent_reopen_regenerates_headers_and_retains_cookies(
    metadata_site, pinned_browser_runtime, tmp_path, enabled
):
    site, requests = metadata_site
    identities = []
    for index, current_enabled in enumerate((enabled, not enabled, enabled)):
        manager = InstanceManager(
            BrowserServerConfig(metadata_headers_enabled=current_enabled), browser_runtime=pinned_browser_runtime
        )
        try:
            record = await manager.create("profile", profile_dir=str(tmp_path))
            page = await manager.target_page("profile")
            await page.goto(f"{site}/profile-{index}")
            identities.append((record.instance_id, manager.page_id("profile", page)))
            if index == 0:
                await record.context.add_cookies(
                    [{"name": "retained", "value": "yes", "url": site, "expires": time.time() + 86400}]
                )
                assert any(cookie.get("name") == "retained" for cookie in await record.context.cookies())
            else:
                assert any(cookie.get("name") == "retained" for cookie in await record.context.cookies())
            headers = next(headers for path, headers, _body in requests if path == f"/profile-{index}")
            assert metadata(headers) == (
                {
                    f"{PREFIX}instance-name": "profile",
                    f"{PREFIX}instance-id": record.instance_id,
                    f"{PREFIX}page-id": manager.page_id("profile", page),
                }
                if current_enabled
                else {}
            )
            if not current_enabled:
                assert not record.state.page_header_tasks
        finally:
            await manager.shutdown_all()
    assert len(set(identities)) == 3


async def test_metadata_preserves_enabled_http_cache(metadata_site, pinned_browser_runtime):
    site, requests = metadata_site
    manager = InstanceManager(BrowserServerConfig(enable_cache=True), browser_runtime=pinned_browser_runtime)
    try:
        record = await manager.create("cache")
        page = await manager.target_page("cache")
        await page.goto(f"{site}/ready")
        first = await page.evaluate("fetch('/cache').then(response => response.text())")
        second = await page.evaluate("fetch('/cache').then(response => response.text())")
        assert first == second
        sent = [headers for path, headers, _body in requests if path == "/cache"]
        assert len(sent) == 1
        assert metadata(sent[0]) == {
            f"{PREFIX}instance-name": "cache",
            f"{PREFIX}instance-id": record.instance_id,
            f"{PREFIX}page-id": manager.page_id("cache", page),
        }
    finally:
        await manager.shutdown_all()
