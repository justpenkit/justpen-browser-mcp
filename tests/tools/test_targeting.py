"""Registered tool target contracts with independently configured page owners."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.tools import register_all

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_frames_enumerates_parent_identity(manager):
    rec = await manager.create("target")
    page = MagicMock()
    page.is_closed.return_value = False
    main, child = MagicMock(), MagicMock()
    for frame in (main, child):
        frame.page = page
        frame.is_detached.return_value = False
        frame.name = "child" if frame is child else ""
        frame.url = "https://example.test"
    main.parent_frame = None
    child.parent_frame = main
    page.main_frame = main
    page.frames = [main, child]
    rec.context.pages = [page]
    pid = manager.page_id("target", page)
    mcp = FastMCP("targeting")
    register_all(mcp, manager)
    async with Client(mcp) as client:
        result = await client.call_tool("browser_frames", {"instance": "target", "page_id": pid})
    assert result.structured_content is not None
    data = result.structured_content["data"]
    assert data["frames"][0]["is_main"] is True
    assert data["frames"][1]["is_main"] is False
    assert data["page_id"] == pid
    assert data["frames"][1]["parent_frame_id"] == data["main_frame_id"]
    assert data["frames"][1]["frame_id"] != data["main_frame_id"]


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("browser_navigate", {"url": "https://example.test"}),
        ("browser_navigate_back", {}),
        ("browser_wait_for", {"time": 0}),
        ("browser_snapshot", {}),
        ("browser_evaluate", {"expression": "1"}),
        ("browser_generate_locator", {"selector": "input"}),
        ("browser_click", {"ref": "e1"}),
        ("browser_type", {"ref": "e1", "text": "x"}),
        ("browser_fill_form", {"fields": []}),
        ("browser_select_option", {"ref": "e1", "value": "x"}),
        ("browser_hover", {"ref": "e1"}),
        ("browser_drag", {"source_ref": "e1", "target_ref": "e2"}),
        ("browser_press_key", {"key": "Tab"}),
        ("browser_mouse_click_xy", {"x": 1, "y": 2}),
        ("browser_mouse_move_xy", {"x": 1, "y": 2}),
        ("browser_mouse_down", {}),
        ("browser_mouse_up", {}),
        ("browser_mouse_drag_xy", {"from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4}),
        ("browser_mouse_wheel", {"delta_y": 1}),
        ("browser_resize", {"width": 800, "height": 600}),
        ("browser_screenshot", {}),
        ("browser_close", {}),
        ("browser_verify_element_visible", {"ref": "e1"}),
        ("browser_verify_list_visible", {"refs": ["e1"]}),
        ("browser_verify_text_visible", {"text": "x"}),
        ("browser_verify_value", {"ref": "e1", "expected_value": "x"}),
        ("browser_run_code", {"code": "return 1"}),
        ("browser_file_upload", {}),
        ("browser_handle_dialog", {"accept": False}),
        ("browser_set_cookies", {"cookies": []}),
        ("browser_clear_local_storage", {}),
    ],
)
async def test_every_targeted_tool_rejects_unknown_page_without_mutation(manager, tool_name, arguments):
    rec = await manager.create("target")
    mcp = FastMCP("all-targets")
    register_all(mcp, manager)
    async with Client(mcp) as client:
        response = await client.call_tool(tool_name, {"instance": "target", "page_id": "unknown", **arguments})
    assert response.data["error_type"] == "page_not_found"
    assert rec.state.active_page is None
    rec.context.new_page.assert_not_awaited()
    rec.context.add_cookies.assert_not_called()


async def test_explicit_close_preserves_other_selected_page(manager):
    rec = await manager.create("target")
    selected, closed = MagicMock(), MagicMock()
    rec.context.pages = [selected, closed]
    selected.is_closed.return_value = closed.is_closed.return_value = False
    closed.close = AsyncMock(side_effect=lambda: rec.context.pages.remove(closed))
    manager.set_active_page("target", 0)
    mcp = FastMCP("close-target")
    register_all(mcp, manager)
    async with Client(mcp) as client:
        response = await client.call_tool(
            "browser_close", {"instance": "target", "page_id": manager.page_id("target", closed)}
        )
    assert response.data["status"] == "success"
    assert rec.state.active_page is selected
    selected.close.assert_not_called()
