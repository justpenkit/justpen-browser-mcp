"""Smoke test validating the e2e harness: real InstanceManager, real Camoufox,
a real FastMCP client, and the local static test site all wired together.
"""

import pytest

from .conftest import call


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning")
async def test_harness_navigates(e2e_client, test_site):
    created = await call(e2e_client, "browser_create_instance", {"name": "s1"})
    assert created["status"] == "success"
    nav = await call(e2e_client, "browser_navigate", {"instance": "s1", "url": f"{test_site}/index.html"})
    assert nav["status"] == "success"
    health = await call(e2e_client, "browser_health", {})
    assert health["data"]["instance_count"] == 1
