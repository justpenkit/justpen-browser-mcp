"""End-to-end tests for multi-instance isolation. Requires real Camoufox binary."""

import time

import pytest

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager


@pytest.fixture
async def real_manager():
    cfg = BrowserServerConfig(log_level="INFO", max_instances=5)
    mgr = InstanceManager(cfg)
    yield mgr
    await mgr.shutdown_all()


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning")
async def test_two_ephemeral_instances_are_isolated(real_manager):
    a = await real_manager.create("alice")
    b = await real_manager.create("bob")

    page_a = await real_manager.active_page("alice")
    await page_a.goto("https://example.com")
    await a.context.add_cookies([{"name": "isolation", "value": "alice", "domain": "example.com", "path": "/"}])

    cookies_b = await b.context.cookies()
    assert all(c["name"] != "isolation" or c["value"] != "alice" for c in cookies_b)


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning")
async def test_persistent_instance_survives_destroy_create_cycle(tmp_path):
    cfg = BrowserServerConfig(log_level="INFO", max_instances=5)
    mgr = InstanceManager(cfg)
    try:
        rec = await mgr.create("alice", profile_dir=str(tmp_path))
        page = await mgr.active_page("alice")
        await page.goto("https://example.com")
        # expires must be set: session cookies (expires=-1) are in-memory only in Firefox
        # and are not written to the profile's cookies.sqlite. A future timestamp forces
        # the cookie to be treated as a persistent cookie and flushed to disk on close.
        await rec.context.add_cookies(
            [{"name": "persist", "value": "yes", "domain": "example.com", "path": "/", "expires": time.time() + 86400}]
        )
        await mgr.destroy("alice")

        rec2 = await mgr.create("alice", profile_dir=str(tmp_path))
        cookies = await rec2.context.cookies()
        assert any(c.get("name") == "persist" and c.get("value") == "yes" for c in cookies)
    finally:
        await mgr.shutdown_all()


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning")
async def test_shutdown_all_closes_multiple_live_instances(real_manager):
    await real_manager.create("a")
    await real_manager.create("b")
    await real_manager.create("c")
    assert len(await real_manager.list()) == 3
    await real_manager.shutdown_all()
    assert await real_manager.list() == []
