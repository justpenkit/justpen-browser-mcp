"""Tests for browser_create_instance / browser_destroy_instance / browser_list_instances."""

import pytest
from fastmcp import FastMCP

import justpen_browser_mcp.tools.lifecycle as lifecycle
from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager


@pytest.fixture
def mcp():
    return FastMCP("test")


async def _call(mcp_instance, tool_name, **kwargs):
    """Resolve and invoke a fastmcp tool by name from within tests."""
    tool = await mcp_instance.get_tool(tool_name)
    return await tool.fn(**kwargs)


@pytest.mark.asyncio
async def test_create_instance_tool_registers_and_returns_summary(mcp, manager):
    lifecycle.register(mcp, manager)
    result = await _call(mcp, "browser_create_instance", name="alice")
    assert result["status"] == "success"
    assert result["instance"] == "alice"
    assert result["data"]["name"] == "alice"
    assert result["data"]["mode"] == "ephemeral"


@pytest.mark.asyncio
async def test_create_instance_tool_persistent_mode(mcp, manager, tmp_path):
    lifecycle.register(mcp, manager)
    result = await _call(mcp, "browser_create_instance", name="alice", profile_dir=str(tmp_path))
    assert result["data"]["mode"] == "persistent"
    assert result["data"]["profile_dir"] == str(tmp_path)


@pytest.mark.asyncio
async def test_destroy_instance_tool(mcp, manager):
    lifecycle.register(mcp, manager)
    await _call(mcp, "browser_create_instance", name="alice")
    result = await _call(mcp, "browser_destroy_instance", name="alice")
    assert result["status"] == "success"
    assert result["instance"] == "alice"


@pytest.mark.asyncio
async def test_destroy_instance_missing_returns_error(mcp, manager):
    lifecycle.register(mcp, manager)
    result = await _call(mcp, "browser_destroy_instance", name="nope")
    assert result["status"] == "error"
    assert result["error_type"] == "instance_not_found"


@pytest.mark.asyncio
async def test_list_instances_tool_empty(mcp, manager):
    lifecycle.register(mcp, manager)
    result = await _call(mcp, "browser_list_instances")
    assert result["status"] == "success"
    assert result["data"]["instances"] == []


@pytest.mark.asyncio
async def test_list_instances_returns_summaries(mcp, manager, tmp_path):
    lifecycle.register(mcp, manager)
    await _call(mcp, "browser_create_instance", name="alice", profile_dir=str(tmp_path))
    await _call(mcp, "browser_create_instance", name="bob")
    result = await _call(mcp, "browser_list_instances")
    modes = {i["name"]: i["mode"] for i in result["data"]["instances"]}
    assert modes == {"alice": "persistent", "bob": "ephemeral"}


@pytest.mark.asyncio
async def test_create_instance_duplicate_returns_error(mcp, manager):
    lifecycle.register(mcp, manager)
    await _call(mcp, "browser_create_instance", name="alice")
    result = await _call(mcp, "browser_create_instance", name="alice")
    assert result["status"] == "error"
    assert result["error_type"] == "instance_already_exists"


@pytest.mark.asyncio
async def test_create_instance_profile_dir_collision_returns_error(mcp, manager, tmp_path):
    lifecycle.register(mcp, manager)
    await _call(mcp, "browser_create_instance", name="alice", profile_dir=str(tmp_path))
    result = await _call(mcp, "browser_create_instance", name="bob", profile_dir=str(tmp_path))
    assert result["status"] == "error"
    assert result["error_type"] == "profile_dir_in_use"


@pytest.mark.asyncio
async def test_create_instance_limit_exceeded_returns_error(mcp, mock_launch):
    """browser_create_instance surfaces InstanceLimitExceededError as an error envelope."""
    cfg = BrowserServerConfig(log_level="INFO", max_instances=1)
    local_mgr = InstanceManager(cfg)
    lifecycle.register(mcp, local_mgr)
    try:
        await _call(mcp, "browser_create_instance", name="alice")
        result = await _call(mcp, "browser_create_instance", name="bob")
        assert result["status"] == "error"
        assert result["error_type"] == "instance_limit_exceeded"
    finally:
        await local_mgr.shutdown_all()
