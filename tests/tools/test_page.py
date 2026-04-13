"""Tests for tools/page.py — browser_close."""

from unittest.mock import AsyncMock, MagicMock


class TestBrowserClose:
    async def test_closes_active_page(self, mcp_client, mock_ctx_mgr):
        page = MagicMock()
        page.close = AsyncMock()
        ctx = MagicMock()
        ctx.pages = [page]
        ctx._active_page_index = 0
        mock_ctx_mgr.get.return_value = ctx
        mock_ctx_mgr.active_page.return_value = page

        result = await mcp_client.call_tool("browser_close", {"context": "admin"})
        assert result.data["status"] == "success"
        page.close.assert_awaited_once()

    async def test_unknown_context(self, mcp_client, mock_ctx_mgr):
        from justpen_browser_mcp.errors import ContextNotFoundError

        mock_ctx_mgr.get.side_effect = ContextNotFoundError("missing")
        result = await mcp_client.call_tool("browser_close", {"context": "admin"})
        assert result.data["error_type"] == "context_not_found"
