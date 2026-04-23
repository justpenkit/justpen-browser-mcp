"""Tests for tools/page.py — browser_close."""

from unittest.mock import AsyncMock, MagicMock

from justpen_browser_mcp.errors import InstanceNotFoundError


class TestBrowserClose:
    async def test_closes_active_page(self, mcp_client, mock_ctx_mgr):
        page = MagicMock()
        page.close = AsyncMock()
        ctx = MagicMock()
        ctx.pages = [page]
        rec = MagicMock()
        rec.context = ctx
        mock_ctx_mgr.state.return_value.active_page_index = 0
        mock_ctx_mgr.get.return_value = rec
        mock_ctx_mgr.active_page.return_value = page

        result = await mcp_client.call_tool("browser_close", {"instance": "admin"})
        assert result.data["status"] == "success"
        page.close.assert_awaited_once()

    async def test_unknown_instance(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.get.side_effect = InstanceNotFoundError("missing")
        result = await mcp_client.call_tool("browser_close", {"instance": "admin"})
        assert result.data["error_type"] == "instance_not_found"
