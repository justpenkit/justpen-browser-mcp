"""End-to-end tests for the cookie and localStorage tools.

Covers browser_get_cookies, browser_set_cookies, browser_clear_cookies, and the
localStorage set/get/clear trio against the local e2e test site.
"""

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


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
    await call(e2e_client, "browser_create_instance", {"name": "c4"})
    await call(e2e_client, "browser_navigate", {"instance": "c4", "url": f"{test_site}/index.html"})
    origin = test_site

    setr = await call(
        e2e_client,
        "browser_set_local_storage",
        {"instance": "c4", "origin": origin, "items": {"k": "v"}},
    )
    assert setr["status"] == "success"
    assert setr["data"]["set_count"] == 1

    got = await call(e2e_client, "browser_get_local_storage", {"instance": "c4", "origin": origin})
    assert got["status"] == "success"
    assert got["data"]["items"] == {"k": "v"}

    single = await call(
        e2e_client,
        "browser_get_local_storage",
        {"instance": "c4", "origin": origin, "key": "k"},
    )
    assert single["status"] == "success"
    assert single["data"]["value"] == "v"

    cleared = await call(e2e_client, "browser_clear_local_storage", {"instance": "c4", "origin": origin})
    assert cleared["status"] == "success"
    assert cleared["data"]["cleared"] is True

    after = await call(e2e_client, "browser_get_local_storage", {"instance": "c4", "origin": origin})
    assert after["status"] == "success"
    assert after["data"]["items"] == {}
