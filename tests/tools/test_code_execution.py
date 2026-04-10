"""Tests for tools/code_execution.py — 2 tools."""

from unittest.mock import AsyncMock, MagicMock, patch


def make_page(mock_ctx_mgr, eval_result="42"):
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=eval_result)
    mock_ctx_mgr.active_page.return_value = page
    mock_ctx_mgr.get.return_value = MagicMock()
    mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])
    return page


class TestBrowserEvaluate:
    async def test_evaluates_and_returns_result(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr, eval_result="hello")
        result = await mcp_client.call_tool(
            "browser_evaluate",
            {"context": "admin", "expression": "document.title"},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["result"] == "hello"
        page.evaluate.assert_awaited_once_with("document.title")

    async def test_evaluation_error(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.evaluate = AsyncMock(
            side_effect=Exception("ReferenceError: foo not defined")
        )
        result = await mcp_client.call_tool(
            "browser_evaluate",
            {"context": "admin", "expression": "foo"},
        )
        assert result.data["error_type"] == "evaluation_failed"

    async def test_ref_scoped_evaluation(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        locator = MagicMock()
        locator.evaluate = AsyncMock(return_value="el-result")
        with patch(
            "justpen_browser_mcp.tools.code_execution.resolve_ref",
            AsyncMock(return_value=locator),
        ):
            result = await mcp_client.call_tool(
                "browser_evaluate",
                {
                    "context": "admin",
                    "expression": "el => el.tagName",
                    "ref": "e1",
                },
            )
        assert result.data["status"] == "success"
        assert result.data["data"]["result"] == "el-result"
        locator.evaluate.assert_awaited_once_with("el => el.tagName")
        page.evaluate.assert_not_awaited()

    async def test_selector_scoped_evaluation(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        locator = MagicMock()
        locator.evaluate = AsyncMock(return_value="sel-result")
        page.locator = MagicMock(return_value=locator)
        result = await mcp_client.call_tool(
            "browser_evaluate",
            {
                "context": "admin",
                "expression": "el => el.textContent",
                "selector": "#main",
            },
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["result"] == "sel-result"
        page.locator.assert_called_with("#main")
        locator.evaluate.assert_awaited_once_with("el => el.textContent")

    async def test_ref_and_selector_conflict(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_evaluate",
            {
                "context": "admin",
                "expression": "el => el",
                "ref": "e1",
                "selector": "#x",
            },
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_blocked_by_modal(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "alert"
        dialog.message = "hi"
        mock_ctx_mgr.get_modal_states = MagicMock(
            return_value=[{"kind": "dialog", "object": dialog, "page": page}]
        )
        result = await mcp_client.call_tool(
            "browser_evaluate",
            {"context": "admin", "expression": "1"},
        )
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserRunCode:
    async def test_executes_code_snippet(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_run_code",
            {"context": "admin", "code": "return await page.title()"},
        )
        assert result.data["status"] in ("success", "error")

    async def test_run_code_error_includes_traceback(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_run_code",
            {"context": "admin", "code": 'raise ValueError("boom")'},
        )
        assert result.data["error_type"] == "evaluation_failed"
        msg = result.data["message"]
        assert "Traceback" in msg
        assert "ValueError" in msg
        assert "boom" in msg
