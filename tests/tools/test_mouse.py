"""Tests for tools/mouse.py — 6 mouse positional tools."""

from unittest.mock import AsyncMock, MagicMock


def make_page(mock_ctx_mgr):
    page = MagicMock()
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    page.mouse.move = AsyncMock()
    page.mouse.down = AsyncMock()
    page.mouse.up = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    mock_ctx_mgr.active_page.return_value = page
    mock_ctx_mgr.get.return_value = MagicMock()
    mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])
    return page


class TestMouseTools:
    async def test_click_xy(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_click_xy",
            {"context": "admin", "x": 100, "y": 200},
        )
        assert result.data["status"] == "success"
        page.mouse.click.assert_awaited_once_with(100, 200, button="left", click_count=1, delay=0)

    async def test_click_xy_right_button(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        await mcp_client.call_tool(
            "browser_mouse_click_xy",
            {"context": "admin", "x": 50, "y": 75, "button": "right"},
        )
        page.mouse.click.assert_awaited_once_with(50, 75, button="right", click_count=1, delay=0)

    async def test_click_xy_with_click_count(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_click_xy",
            {"context": "admin", "x": 10, "y": 20, "click_count": 2},
        )
        assert result.data["status"] == "success"
        page.mouse.click.assert_awaited_once_with(10, 20, button="left", click_count=2, delay=0)

    async def test_click_xy_with_delay(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_click_xy",
            {"context": "admin", "x": 10, "y": 20, "delay_ms": 100},
        )
        assert result.data["status"] == "success"
        page.mouse.click.assert_awaited_once_with(10, 20, button="left", click_count=1, delay=100)

    async def test_move_xy(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_move_xy",
            {"context": "admin", "x": 10, "y": 20},
        )
        assert result.data["status"] == "success"
        page.mouse.move.assert_awaited_once_with(10, 20)

    async def test_mouse_down(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_mouse_down", {"context": "admin"})
        assert result.data["status"] == "success"
        page.mouse.down.assert_awaited_once_with(button="left")

    async def test_mouse_up(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_mouse_up", {"context": "admin"})
        assert result.data["status"] == "success"
        page.mouse.up.assert_awaited_once_with(button="left")

    async def test_drag_xy(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_drag_xy",
            {"context": "admin", "from_x": 10, "from_y": 20, "to_x": 30, "to_y": 40},
        )
        assert result.data["status"] == "success"
        page.mouse.move.assert_any_await(10, 20)
        page.mouse.down.assert_awaited_once()
        page.mouse.move.assert_any_await(30, 40)
        page.mouse.up.assert_awaited_once()

    async def test_wheel(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_wheel",
            {"context": "admin", "delta_x": 0, "delta_y": 100},
        )
        assert result.data["status"] == "success"
        page.mouse.wheel.assert_awaited_once_with(0, 100)

    async def test_wheel_default_zero(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_wheel",
            {"context": "admin", "delta_y": 50},
        )
        assert result.data["status"] == "success"
        page.mouse.wheel.assert_awaited_once_with(0, 50)

    async def test_wheel_both_zero_invalid(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_wheel",
            {"context": "admin"},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_drag_xy_post_stabilization(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_mouse_drag_xy",
            {"context": "admin", "from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4},
        )
        assert result.data["status"] == "success"
        page.wait_for_load_state.assert_awaited_once_with("domcontentloaded", timeout=2000)

    async def test_modal_guard(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "alert"
        dialog.message = "hi"
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[{"kind": "dialog", "object": dialog, "page": page}])
        result = await mcp_client.call_tool(
            "browser_mouse_click_xy",
            {"context": "admin", "x": 1, "y": 2},
        )
        assert result.data["error_type"] == "modal_state_blocked"
        page.mouse.click.assert_not_awaited()
