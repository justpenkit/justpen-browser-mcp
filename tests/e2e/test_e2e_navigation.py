"""End-to-end tests for navigation tools: browser_navigate, browser_navigate_back,
browser_wait_for. Drives a real Camoufox instance through a real FastMCP client
against the local static test site.
"""

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


async def _mk(client, name="n1"):
    await call(client, "browser_create_instance", {"name": name})
    return name


async def test_navigate_returns_url_and_title(e2e_client, test_site):
    n = await _mk(e2e_client)
    r = await call(e2e_client, "browser_navigate", {"instance": n, "url": f"{test_site}/index.html"})
    assert r["status"] == "success"
    assert r["data"]["url"] == f"{test_site}/index.html"
    assert r["data"]["title"] == "Index"


async def test_navigate_then_back_returns_to_previous_url(e2e_client, test_site):
    n = await _mk(e2e_client)
    first = await call(e2e_client, "browser_navigate", {"instance": n, "url": f"{test_site}/index.html"})
    assert first["status"] == "success"
    second = await call(e2e_client, "browser_navigate", {"instance": n, "url": f"{test_site}/second.html"})
    assert second["status"] == "success"
    assert second["data"]["url"] == f"{test_site}/second.html"

    back = await call(e2e_client, "browser_navigate_back", {"instance": n})
    assert back["status"] == "success"
    assert back["data"]["url"] == f"{test_site}/index.html"


async def test_navigate_invalid_url_returns_error_envelope(e2e_client):
    n = await _mk(e2e_client)
    r = await call(e2e_client, "browser_navigate", {"instance": n, "url": "http://127.0.0.1:1/nope"})
    assert r["status"] == "error"
    assert r["error_type"] in {"navigation_failed", "navigation_timeout"}


async def test_wait_for_selector_text_visible(e2e_client, test_site):
    n = await _mk(e2e_client)
    await call(e2e_client, "browser_navigate", {"instance": n, "url": f"{test_site}/index.html"})
    r = await call(e2e_client, "browser_wait_for", {"instance": n, "text": "Home"})
    assert r["status"] == "success"
    assert r["data"]["waited_for"] == "text='Home'"


async def test_wait_for_missing_params_is_invalid(e2e_client):
    n = await _mk(e2e_client)
    r = await call(e2e_client, "browser_wait_for", {"instance": n})
    assert r["status"] == "error"
    assert r["error_type"] == "invalid_params"
