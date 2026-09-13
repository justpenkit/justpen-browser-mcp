"""Real-browser outcomes through registered tools and local HTTP evidence."""

from __future__ import annotations

import asyncio
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager
from justpen_browser_mcp.tools import register_all

from .conftest import call

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox._warnings.LeakWarning"),
]

HTML = b"""<!doctype html><title>Action outcomes</title>
<input aria-label="Request" oninput="fetch('/save', {method:'POST', body:this.value})">
<input aria-label="DOM" oninput="document.querySelector('#state').textContent='Ready'">
<input aria-label="SPA" oninput="history.pushState({}, '', '/next')">
<div id="state">Waiting</div>
<button id="popup" onclick="window.open('/popup')">Popup</button>
<a id="download" href="/attachment">Download</a>
<button id="confirm" onclick="if(confirm('Continue?')) document.querySelector('#state').textContent='Confirmed'">Confirm</button>
"""


@pytest.fixture
def outcome_site() -> Iterator[tuple[str, list[bytes], threading.Event, threading.Event]]:
    received = []
    delayed_started = threading.Event()
    delayed_release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = b"download bytes\x00\xff" if self.path == "/attachment" else HTML
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream" if self.path == "/attachment" else "text/html")
            if self.path == "/attachment":
                self.send_header("Content-Disposition", 'attachment; filename="report.bin"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            received.append(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if received[-1] == b"delayed":
                delayed_started.set()
                delayed_release.wait(timeout=5)
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received, delayed_started, delayed_release
    finally:
        delayed_release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
async def observation_browser(outcome_site, request):
    url, received, _started, _release = outcome_site
    manager = InstanceManager(BrowserServerConfig(operation_timeout_seconds=8))
    server = FastMCP("outcomes")
    register_all(server, manager)
    try:
        await manager.create("outcomes")
        page = await manager.active_page("outcomes")
        await page.goto(url)
        manager._config = BrowserServerConfig(operation_timeout_seconds=getattr(request, "param", 8))
        async with Client(server) as client:
            yield client, manager, page, url, received
    finally:
        await manager.shutdown_all()


async def input_ref(client, label):
    snapshot = await call(client, "browser_snapshot", {"instance": "outcomes"})
    match = re.search(r'textbox "' + label + r'" \[ref=([^\]]+)\]', snapshot["data"]["snapshot"])
    assert match is not None, snapshot
    return match[1]


async def test_response_headers_observed_once_even_for_http_error(observation_browser):
    client, _manager, _page, url, received = observation_browser
    ref = await input_ref(client, "Request")
    result = await call(
        client,
        "browser_type",
        {
            "instance": "outcomes",
            "ref": ref,
            "text": "once",
            "wait_for": {"kind": "response", "url": url + "/save", "method": "POST", "status": 500},
        },
    )
    assert result["status"] == "success", result
    assert result["data"]["observation"]["status"] == 500
    assert received == [b"once"]


async def test_dom_postcondition_and_timeout_release_action_lock(observation_browser):
    client, _manager, _page, url, _received = observation_browser
    ref = await input_ref(client, "DOM")
    timed_out = await call(
        client,
        "browser_type",
        {
            "instance": "outcomes",
            "ref": ref,
            "text": "once",
            "wait_for": {"kind": "response", "url": url + "/missing", "timeout_ms": 20},
        },
    )
    assert timed_out["error_type"] == "observation_timeout", timed_out
    assert timed_out["data"]["action_completed"] is True
    completed = await call(
        client,
        "browser_type",
        {"instance": "outcomes", "ref": ref, "text": "again", "wait_for": {"kind": "text", "text": "Ready"}},
    )
    assert completed["data"]["observation"]["matched"] is True


async def test_spa_navigation_requires_new_event(observation_browser):
    client, _manager, _page, url, _received = observation_browser
    ref = await input_ref(client, "DOM")
    timed_out = await call(
        client,
        "browser_type",
        {
            "instance": "outcomes",
            "ref": ref,
            "text": "once",
            "wait_for": {"kind": "url", "url": url + "/", "timeout_ms": 20},
        },
    )
    assert timed_out["error_type"] == "observation_timeout"
    ref = await input_ref(client, "SPA")
    result = await call(
        client,
        "browser_type",
        {"instance": "outcomes", "ref": ref, "text": "next", "wait_for": {"kind": "url", "url": url + "/next"}},
    )
    assert result["data"]["observation"]["url"] == url + "/next"


async def test_popup_keeps_selection_and_download_handle_saves_bytes(observation_browser, tmp_path):
    client, manager, page, _url, _received = observation_browser
    original = manager.page_id("outcomes", page)
    await page.locator("#popup").focus()
    popup = await call(
        client, "browser_press_key", {"instance": "outcomes", "key": "Enter", "wait_for": {"kind": "popup"}}
    )
    assert popup["status"] == "success", popup
    tabs = await call(client, "browser_tabs", {"instance": "outcomes", "action": "list"})
    assert popup["data"]["observation"]["page_id"] in {tab["page_id"] for tab in tabs["data"]["tabs"]}
    assert manager.page_id("outcomes", await manager.active_page("outcomes")) == original
    await page.locator("#download").focus()
    download = await call(
        client,
        "browser_press_key",
        {"instance": "outcomes", "key": "Enter", "page_id": original, "wait_for": {"kind": "download"}},
    )
    assert download["status"] == "success", download
    destination = tmp_path / "report.bin"
    saved = await call(
        client,
        "browser_download_save",
        {
            "instance": "outcomes",
            "download_id": download["data"]["observation"]["download_id"],
            "path": str(destination),
        },
    )
    assert saved["status"] == "success", saved
    assert destination.read_bytes() == b"download bytes\x00\xff"


async def test_dialog_recovery_runs_during_observed_action(observation_browser):
    client, manager, page, _url, _received = observation_browser
    await page.locator("#confirm").focus()
    dialog_opened = asyncio.Event()
    page.once("dialog", lambda _dialog: dialog_opened.set())
    action = asyncio.create_task(
        call(
            client,
            "browser_press_key",
            {"instance": "outcomes", "key": "Enter", "wait_for": {"kind": "text", "text": "Confirmed"}},
        )
    )
    try:
        async with asyncio.timeout(4):
            await dialog_opened.wait()
        handled = await call(
            client,
            "browser_handle_dialog",
            {"instance": "outcomes", "accept": True, "page_id": manager.page_id("outcomes", page)},
        )
        assert handled["status"] == "success", handled
        result = await action
        assert result["status"] == "success", result
    finally:
        if not action.done():
            action.cancel()
        await asyncio.gather(action, return_exceptions=True)


async def test_explicit_frame_filters_same_url_response(observation_browser):
    client, manager, page, url, received = observation_browser
    await page.evaluate("""() => {
        const frame = document.createElement('iframe');
        frame.srcdoc = `<input aria-label="Child" oninput="fetch('/save', {method:'POST', body:this.value})">`;
        document.body.append(frame);
    }""")
    await page.frame_locator("iframe").get_by_label("Child").wait_for()
    child = next(frame for frame in page.frames if frame is not page.main_frame)
    await page.evaluate("""() => {
        document.querySelector('[aria-label="Request"]').oninput = function() {
            document.querySelector('iframe').contentWindow.fetch('/save', {method:'POST', body:this.value});
        };
    }""")
    top_id = manager.frame_id("outcomes", page.main_frame)
    top_snapshot = await call(client, "browser_snapshot", {"instance": "outcomes", "frame_id": top_id})
    match = re.search(r'textbox "Request" \[ref=([^\]]+)\]', top_snapshot["data"]["snapshot"])
    assert match is not None
    ignored = await call(
        client,
        "browser_type",
        {
            "instance": "outcomes",
            "frame_id": top_id,
            "ref": match[1],
            "text": "wrong-frame",
            "wait_for": {"kind": "response", "url": url + "/save", "timeout_ms": 100},
        },
    )
    assert ignored["error_type"] == "observation_timeout", ignored
    child_id = manager.frame_id("outcomes", child)
    snapshot = await call(client, "browser_snapshot", {"instance": "outcomes", "frame_id": child_id})
    match = re.search(r'textbox "Child" \[ref=([^\]]+)\]', snapshot["data"]["snapshot"])
    assert match is not None
    matched = await call(
        client,
        "browser_type",
        {
            "instance": "outcomes",
            "frame_id": child_id,
            "ref": match[1],
            "text": "right-frame",
            "wait_for": {"kind": "response", "url": url + "/save"},
        },
    )
    assert matched["status"] == "success", matched
    assert matched["data"]["observation"]["frame_id"] == child_id
    assert received[0] == b"wrong-frame"
    assert received[1:]
    assert all(body == b"right-frame" for body in received[1:])


@pytest.mark.parametrize("observation_browser", [0.5], indirect=True)
async def test_outer_deadline_keeps_completion_and_allows_next_action(observation_browser):
    client, _manager, page, url, _received = observation_browser
    ref = await input_ref(client, "DOM")
    result = await call(
        client,
        "browser_type",
        {
            "instance": "outcomes",
            "ref": ref,
            "text": "completed",
            "wait_for": {"kind": "response", "url": url + "/missing", "timeout_ms": 5000},
        },
    )
    assert result["error_type"] == "operation_timeout", result
    assert result["data"]["action_completed"] is True
    assert result["operation"]["retry"] == "inspect_state"
    assert await page.get_by_label("DOM").input_value() == "completed"
    following = await call(client, "browser_type", {"instance": "outcomes", "ref": ref, "text": "following"})
    assert following["status"] == "success", following


async def test_delayed_response_waits_for_headers_after_action(observation_browser, outcome_site):
    client, _manager, page, url, received = observation_browser
    ref = await input_ref(client, "Request")
    task = asyncio.create_task(
        call(
            client,
            "browser_type",
            {
                "instance": "outcomes",
                "ref": ref,
                "text": "delayed",
                "wait_for": {"kind": "response", "url": url + "/save"},
            },
        )
    )
    try:
        assert await asyncio.to_thread(outcome_site[2].wait, 4)
        assert not task.done()
        assert await page.get_by_label("Request").input_value() == "delayed"
        outcome_site[3].set()
        result = await task
        assert result["status"] == "success", result
        assert received == [b"delayed"]
    finally:
        outcome_site[3].set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_hidden_text_wait_requires_all_visible_matches_to_disappear(observation_browser):
    client, _manager, page, _url, _received = observation_browser
    await page.evaluate("""() => {
        document.body.insertAdjacentHTML('beforeend', '<span hidden>Duplicate status</span><span>Duplicate status</span>');
    }""")
    ref = await input_ref(client, "DOM")
    timed_out = await call(
        client,
        "browser_type",
        {
            "instance": "outcomes",
            "ref": ref,
            "text": "first",
            "wait_for": {"kind": "text", "text": "Duplicate status", "state": "hidden", "timeout_ms": 20},
        },
    )
    assert timed_out["error_type"] == "observation_timeout", timed_out
    await page.evaluate("""() => {
        document.querySelector('[aria-label="DOM"]').oninput = () => document.querySelectorAll('span').forEach(span => span.hidden = true);
    }""")
    completed = await call(
        client,
        "browser_type",
        {
            "instance": "outcomes",
            "ref": ref,
            "text": "second",
            "wait_for": {"kind": "text", "text": "Duplicate status", "state": "hidden"},
        },
    )
    assert completed["status"] == "success", completed
