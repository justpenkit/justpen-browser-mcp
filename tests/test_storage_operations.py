"""Storage operation metadata describes the temporary page actually accessed."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.operation_context import current_operation
from justpen_browser_mcp.tools import register_all
from justpen_browser_mcp.tools.cookies import _storage_in_origin

pytestmark = pytest.mark.integration


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


@pytest.mark.parametrize("fail_setup", [False, True])
async def test_storage_awaits_header_setup_before_navigation_and_closes_on_failure(manager, monkeypatch, fail_setup):
    record = await manager.create("headers")
    page = MagicMock()
    page.evaluate = AsyncMock(return_value='{"value": {}}')
    page.goto = AsyncMock()
    page.close = AsyncMock()
    record.context.pages = [page]
    record.context.new_page.return_value = page
    release = asyncio.Event()

    async def prepare(_record, _page):
        assert _record is record
        assert _page is page
        await release.wait()
        if fail_setup:
            raise RuntimeError("header setup failed")

    prepare_mock = AsyncMock(side_effect=prepare)
    monkeypatch.setattr(manager, "ensure_page_headers", prepare_mock)
    operation = asyncio.create_task(
        _storage_in_origin(record.context, "https://storage.test", "get", mgr=manager, instance="headers")
    )
    try:
        await asyncio.sleep(0)
        prepare_mock.assert_awaited_once_with(record, page)
        page.goto.assert_not_awaited()
        release.set()
        if fail_setup:
            with pytest.raises(RuntimeError, match="header setup failed"):
                await operation
            page.goto.assert_not_awaited()
            page.evaluate.assert_not_awaited()
        else:
            assert await operation == {}
            page.goto.assert_awaited_once_with("https://storage.test", wait_until="commit")
        page.close.assert_awaited_once()
    finally:
        release.set()
        await asyncio.gather(operation, return_exceptions=True)
