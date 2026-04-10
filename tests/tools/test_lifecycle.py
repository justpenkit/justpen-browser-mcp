"""Tests for tools/lifecycle.py — 5 context lifecycle tools."""

from justpen_browser_mcp.errors import (
    ContextAlreadyExistsError,
    ContextNotFoundError,
    StateFileNotFoundError,
)


class TestBrowserCreateContext:
    async def test_success_no_state(self, mcp_client, mock_ctx_mgr):
        result = await mcp_client.call_tool(
            "browser_create_context", {"context": "admin"}
        )
        assert result.data["status"] == "success"
        assert result.data["context"] == "admin"
        mock_ctx_mgr.create.assert_awaited_once_with("admin", state_path=None)

    async def test_success_with_state(self, mcp_client, mock_ctx_mgr):
        result = await mcp_client.call_tool(
            "browser_create_context",
            {"context": "admin", "state_path": "/workspace/state/admin.json"},
        )
        assert result.data["status"] == "success"
        mock_ctx_mgr.create.assert_awaited_once_with(
            "admin", state_path="/workspace/state/admin.json"
        )

    async def test_already_exists_error(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.create.side_effect = ContextAlreadyExistsError(
            "Context 'admin' already exists"
        )
        result = await mcp_client.call_tool(
            "browser_create_context", {"context": "admin"}
        )
        assert result.data["status"] == "error"
        assert result.data["error_type"] == "context_already_exists"

    async def test_invalid_state_file(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.create.side_effect = StateFileNotFoundError("State file not found")
        result = await mcp_client.call_tool(
            "browser_create_context",
            {"context": "admin", "state_path": "/nope.json"},
        )
        assert result.data["status"] == "error"
        assert result.data["error_type"] == "state_file_not_found"


class TestBrowserLoadContextState:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        result = await mcp_client.call_tool(
            "browser_load_context_state",
            {"context": "admin", "state_path": "/workspace/state/admin.json"},
        )
        assert result.data["status"] == "success"
        mock_ctx_mgr.load_state.assert_awaited_once_with(
            "admin", "/workspace/state/admin.json"
        )

    async def test_unknown_context(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.load_state.side_effect = ContextNotFoundError(
            "Context 'admin' does not exist"
        )
        result = await mcp_client.call_tool(
            "browser_load_context_state",
            {"context": "admin", "state_path": "/x.json"},
        )
        assert result.data["status"] == "error"
        assert result.data["error_type"] == "context_not_found"


class TestBrowserExportContextState:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        result = await mcp_client.call_tool(
            "browser_export_context_state",
            {"context": "admin", "state_path": "/workspace/out.json"},
        )
        assert result.data["status"] == "success"
        mock_ctx_mgr.export_state.assert_awaited_once_with(
            "admin", "/workspace/out.json"
        )

    async def test_unknown_context(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.export_state.side_effect = ContextNotFoundError("not here")
        result = await mcp_client.call_tool(
            "browser_export_context_state",
            {"context": "admin", "state_path": "/x.json"},
        )
        assert result.data["status"] == "error"
        assert result.data["error_type"] == "context_not_found"


class TestBrowserDestroyContext:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        result = await mcp_client.call_tool(
            "browser_destroy_context", {"context": "admin"}
        )
        assert result.data["status"] == "success"
        mock_ctx_mgr.destroy.assert_awaited_once_with("admin")

    async def test_unknown_context(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.destroy.side_effect = ContextNotFoundError("not here")
        result = await mcp_client.call_tool(
            "browser_destroy_context", {"context": "admin"}
        )
        assert result.data["status"] == "error"
        assert result.data["error_type"] == "context_not_found"


class TestBrowserListContexts:
    async def test_empty(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.list.return_value = []
        result = await mcp_client.call_tool("browser_list_contexts", {})
        assert result.data["status"] == "success"
        assert result.data["data"]["contexts"] == []

    async def test_with_contexts(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.list.return_value = [
            {
                "context": "admin",
                "page_count": 1,
                "active_url": "https://x",
                "cookie_count": 3,
            },
            {
                "context": "viewer",
                "page_count": 0,
                "active_url": None,
                "cookie_count": 0,
            },
        ]
        result = await mcp_client.call_tool("browser_list_contexts", {})
        assert result.data["status"] == "success"
        assert len(result.data["data"]["contexts"]) == 2
