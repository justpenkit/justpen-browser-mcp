"""Storage operation metadata describes the temporary page actually accessed."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.operation_context import current_operation
from justpen_browser_mcp.tools import register_all


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("browser_get_local_storage", {}),
        ("browser_set_local_storage", {"items": {"key": "value"}}),
        ("browser_clear_local_storage", {}),
    ],
)
async def test_storage_reports_temporary_page_before_navigation(manager, tool, arguments):
    record = await manager.create("storage")
    active = MagicMock(is_closed=MagicMock(return_value=False))
    record.context.pages.append(active)
    manager.set_active_page("storage", 0)
    active_id = manager.page_id("storage", active)
    temporary = MagicMock(is_closed=MagicMock(return_value=False))
    temporary.evaluate = AsyncMock(return_value='{"value": {}}')
    navigation_targets = []
    temporary_ids = []

    async def new_page():
        record.context.pages.append(temporary)
        temporary_ids.append(manager.page_id("storage", temporary))
        return temporary

    async def navigate(*_args, **_kwargs):
        operation = current_operation.get()
        assert operation is not None
        navigation_targets.append(operation.page_id)

    async def close():
        record.context.pages.remove(temporary)

    record.context.new_page = AsyncMock(side_effect=new_page)
    temporary.goto = AsyncMock(side_effect=navigate)
    temporary.close = AsyncMock(side_effect=close)
    server = FastMCP("storage-operations")
    register_all(server, manager)
    async with Client(server) as client:
        result = await client.call_tool(tool, {"instance": "storage", "origin": "https://storage.test", **arguments})
    assert result.data["status"] == "success", result.data
    assert result.data["operation"]["instance_id"] == record.instance_id
    assert result.data["operation"]["page_id"] == temporary_ids[0]
    assert navigation_targets == temporary_ids
    assert temporary_ids[0] != active_id
    assert record.state.active_page is active
    assert record.context.pages == [active]
