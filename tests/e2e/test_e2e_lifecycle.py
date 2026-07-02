"""End-to-end tests for instance lifecycle tools: browser_create_instance,
browser_list_instances, browser_destroy_instance.
"""

import pytest

from .conftest import call

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.filterwarnings("ignore::camoufox.warnings.LeakWarning"),
]


async def test_create_list_destroy_round_trip(e2e_client):
    created = await call(e2e_client, "browser_create_instance", {"name": "a"})
    assert created["status"] == "success"
    assert created["data"]["name"] == "a"
    assert created["data"]["mode"] == "ephemeral"
    assert created["data"]["profile_dir"] is None

    lst = await call(e2e_client, "browser_list_instances", {})
    assert lst["status"] == "success"
    assert any(i["name"] == "a" for i in lst["data"]["instances"])

    d = await call(e2e_client, "browser_destroy_instance", {"name": "a"})
    assert d["status"] == "success"

    lst_after = await call(e2e_client, "browser_list_instances", {})
    assert all(i["name"] != "a" for i in lst_after["data"]["instances"])


async def test_duplicate_name_errors(e2e_client):
    first = await call(e2e_client, "browser_create_instance", {"name": "dup"})
    assert first["status"] == "success"

    r = await call(e2e_client, "browser_create_instance", {"name": "dup"})
    assert r["status"] == "error"
    assert r["error_type"] == "instance_already_exists"


async def test_destroy_unknown_instance_errors(e2e_client):
    r = await call(e2e_client, "browser_destroy_instance", {"name": "ghost"})
    assert r["status"] == "error"
    assert r["error_type"] == "instance_not_found"


async def test_persistent_profile_create_round_trip(e2e_client, tmp_path):
    profile_dir = str(tmp_path / "profile")
    created = await call(
        e2e_client,
        "browser_create_instance",
        {"name": "persist1", "profile_dir": profile_dir},
    )
    assert created["status"] == "success"
    assert created["data"]["mode"] == "persistent"
    assert created["data"]["profile_dir"] == profile_dir

    d = await call(e2e_client, "browser_destroy_instance", {"name": "persist1"})
    assert d["status"] == "success"
