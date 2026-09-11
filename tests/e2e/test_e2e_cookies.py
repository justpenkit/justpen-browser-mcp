"""End-to-end tests for the cookie and localStorage tools.

Covers browser_get_cookies, browser_set_cookies, browser_clear_cookies, and the
localStorage set/get/clear trio against the local e2e test site.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox._warnings.LeakWarning"),
]


@pytest.fixture
def pending_script_origin():
    """Serve complete HTML whose parser waits for an external script."""
    release = threading.Event()
    response_started = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/pending.js":
                release.wait()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'<!doctype html><title>Pending script</title><script src="/pending.js"></script><body>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            response_started.set()
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", response_started
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("tool", "arguments", "expected"),
    [
        ("browser_set_local_storage", {"items": {"k": "v"}}, {"set_count": 1}),
        ("browser_get_local_storage", {}, {"items": {}}),
        ("browser_clear_local_storage", {}, {"cleared": True}),
    ],
)
async def test_local_storage_needs_origin_commit_not_finished_document(
    e2e_client, test_site, pending_script_origin, tool, arguments, expected
):
    origin, response_started = pending_script_origin
    created = await call(e2e_client, "browser_create_instance", {"name": "streaming"})
    assert created["status"] == "success", created
    navigated = await call(e2e_client, "browser_navigate", {"instance": "streaming", "url": f"{test_site}/index.html"})
    assert navigated["status"] == "success", navigated

    result = await call(e2e_client, tool, {"instance": "streaming", "origin": origin, **arguments})
    assert response_started.is_set()
    assert result["status"] == "success", result
    assert result["data"] == {**expected, "origin": origin}
    active = await call(e2e_client, "browser_evaluate", {"instance": "streaming", "expression": "location.href"})
    assert active["status"] == "success", active
    assert active["data"]["result"] == f"{test_site}/index.html"
    tabs = await call(e2e_client, "browser_tabs", {"instance": "streaming", "action": "list"})
    assert tabs["status"] == "success", tabs
    assert len(tabs["data"]["tabs"]) == 1
    tab = tabs["data"]["tabs"][0]
    assert tab["index"] == 0
    assert tab["url"] == f"{test_site}/index.html"
    assert isinstance(tab["page_id"], str)


async def test_get_cookies_returns_page_set_cookie(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "c1"})
    await call(e2e_client, "browser_navigate", {"instance": "c1", "url": f"{test_site}/cookies.html"})

    got = await call(e2e_client, "browser_get_cookies", {"instance": "c1"})
    assert got["status"] == "success"
    e2e_cookies = [c for c in got["data"]["cookies"] if c["name"] == "e2e"]
    assert len(e2e_cookies) == 1
    assert e2e_cookies[0]["value"] == "yes"


async def test_set_cookies_then_read_back(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "c2"})
    await call(e2e_client, "browser_navigate", {"instance": "c2", "url": f"{test_site}/index.html"})

    # No domain/url supplied -> defaults to the active page hostname (127.0.0.1).
    setr = await call(
        e2e_client,
        "browser_set_cookies",
        {"instance": "c2", "cookies": [{"name": "foo", "value": "bar"}]},
    )
    assert setr["status"] == "success"
    assert setr["data"]["set_count"] == 1

    got = await call(e2e_client, "browser_get_cookies", {"instance": "c2", "name": "foo"})
    assert got["status"] == "success"
    assert len(got["data"]["cookies"]) == 1
    assert got["data"]["cookies"][0]["value"] == "bar"


async def test_clear_cookies_removes_all(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "c3"})
    await call(e2e_client, "browser_navigate", {"instance": "c3", "url": f"{test_site}/cookies.html"})

    before = await call(e2e_client, "browser_get_cookies", {"instance": "c3"})
    assert any(c["name"] == "e2e" for c in before["data"]["cookies"])

    cleared = await call(e2e_client, "browser_clear_cookies", {"instance": "c3"})
    assert cleared["status"] == "success"
    assert cleared["data"] == {"cleared": True}

    after = await call(e2e_client, "browser_get_cookies", {"instance": "c3"})
    assert after["status"] == "success"
    assert after["data"]["cookies"] == []


async def test_local_storage_roundtrip_and_clear(e2e_client, test_site):
    created = await call(e2e_client, "browser_create_instance", {"name": "c4"})
    assert created["status"] == "success", created
    navigated = await call(e2e_client, "browser_navigate", {"instance": "c4", "url": f"{test_site}/index.html"})
    assert navigated["status"] == "success", navigated
    origin = test_site

    setr = await call(
        e2e_client,
        "browser_set_local_storage",
        {"instance": "c4", "origin": origin, "items": {"k": "v"}},
    )
    assert setr["status"] == "success", setr
    assert setr["data"]["set_count"] == 1

    got = await call(e2e_client, "browser_get_local_storage", {"instance": "c4", "origin": origin})
    assert got["status"] == "success", got
    assert got["data"]["items"] == {"k": "v"}

    single = await call(
        e2e_client,
        "browser_get_local_storage",
        {"instance": "c4", "origin": origin, "key": "k"},
    )
    assert single["status"] == "success", single
    assert single["data"]["value"] == "v"

    cleared = await call(e2e_client, "browser_clear_local_storage", {"instance": "c4", "origin": origin})
    assert cleared["status"] == "success", cleared
    assert cleared["data"]["cleared"] is True

    after = await call(e2e_client, "browser_get_local_storage", {"instance": "c4", "origin": origin})
    assert after["status"] == "success", after
    assert after["data"]["items"] == {}

    active = await call(e2e_client, "browser_evaluate", {"instance": "c4", "expression": "location.href"})
    assert active["status"] == "success", active
    assert active["data"]["result"] == f"{test_site}/index.html"
    tabs = await call(e2e_client, "browser_tabs", {"instance": "c4", "action": "list"})
    assert tabs["status"] == "success", tabs
    assert len(tabs["data"]["tabs"]) == 1
    tab = tabs["data"]["tabs"][0]
    assert tab["index"] == 0
    assert tab["url"] == f"{test_site}/index.html"
    assert isinstance(tab["page_id"], str)
