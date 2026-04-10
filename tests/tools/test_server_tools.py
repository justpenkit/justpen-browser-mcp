"""Tests for tools/server_tools.py — browser_status."""

from unittest.mock import MagicMock


class TestBrowserStatus:
    async def test_browser_not_running_no_contexts(
        self, mcp_client, mock_ctx_mgr, mock_launcher
    ):
        mock_launcher.is_running.return_value = False
        mock_ctx_mgr._contexts = {}
        result = await mcp_client.call_tool("browser_status", {})
        assert result.data["status"] == "success"
        assert result.data["data"]["browser_running"] is False
        assert result.data["data"]["active_context_count"] == 0

    async def test_browser_running_with_contexts(
        self, mcp_client, mock_ctx_mgr, mock_launcher
    ):
        mock_launcher.is_running.return_value = True
        mock_ctx_mgr._contexts = {"admin": MagicMock(), "viewer": MagicMock()}
        result = await mcp_client.call_tool("browser_status", {})
        assert result.data["status"] == "success"
        assert result.data["data"]["browser_running"] is True
        assert result.data["data"]["active_context_count"] == 2
        names = {c["context"] for c in result.data["data"]["active_contexts"]}
        assert names == {"admin", "viewer"}

    async def test_does_not_trigger_launch(
        self, mcp_client, mock_ctx_mgr, mock_launcher
    ):
        """browser_status MUST NOT call launcher.get_browser()."""
        mock_launcher.is_running.return_value = False
        await mcp_client.call_tool("browser_status", {})
        mock_launcher.get_browser.assert_not_called()
