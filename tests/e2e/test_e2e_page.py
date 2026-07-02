"""End-to-end tests for the page (tab) lifecycle tool: browser_close.

browser_close closes the active page but must leave the instance itself
alive — verified here via browser_health and browser_list_instances.
"""

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


async def test_close_page_keeps_instance_alive(e2e_client, test_site):
    await call(e2e_client, "browser_create_instance", {"name": "p1"})
    await call(e2e_client, "browser_navigate", {"instance": "p1", "url": f"{test_site}/index.html"})

    r = await call(e2e_client, "browser_close", {"instance": "p1"})
    assert r["status"] == "success"
    assert r["data"]["closed"] is True

    health = await call(e2e_client, "browser_health", {})
    names = [i["name"] for i in health["data"]["instances"]]
    assert "p1" in names

    listed = await call(e2e_client, "browser_list_instances", {})
    listed_names = [i["name"] for i in listed["data"]["instances"]]
    assert "p1" in listed_names


async def test_close_with_no_open_pages_reports_reason(e2e_client):
    await call(e2e_client, "browser_create_instance", {"name": "p2"})

    first = await call(e2e_client, "browser_close", {"instance": "p2"})
    assert first["status"] == "success"

    second = await call(e2e_client, "browser_close", {"instance": "p2"})
    assert second["status"] == "success"
    assert second["data"] == {"closed": False, "reason": "no open pages"}


async def test_close_unknown_instance_returns_error(e2e_client):
    r = await call(e2e_client, "browser_close", {"instance": "does-not-exist"})
    assert r["status"] == "error"
    assert r["error_type"] == "instance_not_found"
