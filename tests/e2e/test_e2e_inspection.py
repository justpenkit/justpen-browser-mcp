"""End-to-end tests for page inspection tools: browser_snapshot, browser_screenshot,
browser_console_messages, browser_network_requests.

Console messages and network requests are collected by event listeners
attached at instance creation, so no manual polling harness is needed beyond
a short browser_wait_for to let async page scripts (setTimeout, fetch) run.
"""

import base64

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


async def test_snapshot_returns_structured_accessibility_tree(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins1"})
    await call(e2e_client, "browser_navigate", {"instance": "ins1", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_snapshot", {"instance": "ins1"})
    assert r["status"] == "success"
    assert r["data"]["url"] == f"{test_site}/index.html"

    snapshot = r["data"]["snapshot"]
    # index.html has an <h1 id="title">Home</h1> and a "Form" link — both
    # must surface as named, ref-annotated accessibility nodes.
    assert 'heading "Home"' in snapshot
    assert "[ref=e" in snapshot
    assert 'link "Form"' in snapshot


async def test_snapshot_selector_mode_omits_refs(e2e_client, test_site):
    """selector= mode returns a scoped aria snapshot WITHOUT ref annotations."""
    await call(e2e_client, "browser_create_instance", {"name": "ins2"})
    await call(e2e_client, "browser_navigate", {"instance": "ins2", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_snapshot", {"instance": "ins2", "selector": "#title"})
    assert r["status"] == "success"
    assert "[ref=" not in r["data"]["snapshot"]
    assert "Home" in r["data"]["snapshot"]


async def test_screenshot_returns_decodable_png(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins3"})
    await call(e2e_client, "browser_navigate", {"instance": "ins3", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_screenshot", {"instance": "ins3"})
    assert r["status"] == "success"
    assert r["data"]["image_format"] == "png"

    raw = base64.b64decode(r["data"]["image_base64"], validate=True)
    # A real PNG viewport screenshot is a substantial, non-trivial blob and
    # starts with the PNG magic bytes.
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(raw) > 1000
    assert r["data"]["width"] == 1280
    assert r["data"]["height"] == 720


async def test_screenshot_rejects_invalid_format(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins4"})
    await call(e2e_client, "browser_navigate", {"instance": "ins4", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_screenshot", {"instance": "ins4", "image_format": "bmp"})
    assert r["status"] == "error"
    assert r["error_type"] == "invalid_params"


async def test_console_messages_captured(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins5"})
    await call(e2e_client, "browser_navigate", {"instance": "ins5", "url": f"{test_site}/console.html"})
    # console.html throws an uncaught error from a setTimeout(0,...) callback,
    # which fires on the next event-loop turn — give it a moment to land.
    await call(e2e_client, "browser_wait_for", {"instance": "ins5", "time": 0.5})

    r = await call(e2e_client, "browser_console_messages", {"instance": "ins5"})
    assert r["status"] == "success"
    messages = r["data"]["messages"]

    assert any(m["type"] == "log" and m["text"] == "log-line" for m in messages)
    assert any(m["type"] == "warning" and m["text"] == "warn-line" for m in messages)
    assert any(m["type"] == "error" and m["text"] == "boom" for m in messages)


async def test_console_messages_filtered_by_level(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins6"})
    await call(e2e_client, "browser_navigate", {"instance": "ins6", "url": f"{test_site}/console.html"})
    await call(e2e_client, "browser_wait_for", {"instance": "ins6", "time": 0.5})

    r = await call(e2e_client, "browser_console_messages", {"instance": "ins6", "level": "error"})
    assert r["status"] == "success"
    messages = r["data"]["messages"]
    assert messages
    assert all(m["type"] == "error" for m in messages)
    assert any(m["text"] == "boom" for m in messages)


async def test_network_requests_captured_excludes_static_by_default(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins7"})
    await call(e2e_client, "browser_navigate", {"instance": "ins7", "url": f"{test_site}/network.html"})
    await call(e2e_client, "browser_wait_for", {"instance": "ins7", "time": 0.5})

    r = await call(e2e_client, "browser_network_requests", {"instance": "ins7"})
    assert r["status"] == "success"
    requests = r["data"]["requests"]

    data_json = [req for req in requests if req["url"].endswith("/data.json")]
    assert len(data_json) == 1
    assert data_json[0]["method"] == "GET"
    assert data_json[0]["status"] == 200
    assert data_json[0]["resource_type"] == "fetch"

    # image resources are filtered out of the default (static=False) view.
    assert not any(req["url"].endswith("/pixel.png") for req in requests)


async def test_network_requests_static_true_includes_image(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins8"})
    await call(e2e_client, "browser_navigate", {"instance": "ins8", "url": f"{test_site}/network.html"})
    await call(e2e_client, "browser_wait_for", {"instance": "ins8", "time": 0.5})

    r = await call(e2e_client, "browser_network_requests", {"instance": "ins8", "static": True})
    assert r["status"] == "success"
    requests = r["data"]["requests"]

    pixel = [req for req in requests if req["url"].endswith("/pixel.png")]
    assert len(pixel) == 1
    assert pixel[0]["resource_type"] == "image"
    assert pixel[0]["status"] == 200


async def test_network_requests_url_filter(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins9"})
    await call(e2e_client, "browser_navigate", {"instance": "ins9", "url": f"{test_site}/network.html"})
    await call(e2e_client, "browser_wait_for", {"instance": "ins9", "time": 0.5})

    r = await call(e2e_client, "browser_network_requests", {"instance": "ins9", "url_filter": r"data\.json$"})
    assert r["status"] == "success"
    requests = r["data"]["requests"]
    assert len(requests) == 1
    assert requests[0]["url"].endswith("/data.json")


async def test_network_requests_invalid_regex_is_invalid_params(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "ins10"})
    await call(e2e_client, "browser_navigate", {"instance": "ins10", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_network_requests", {"instance": "ins10", "url_filter": "["})
    assert r["status"] == "error"
    assert r["error_type"] == "invalid_params"
