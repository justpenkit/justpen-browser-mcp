"""Tests for tools/navigation.py — 3 navigation tools."""

from unittest.mock import AsyncMock, MagicMock

from playwright.async_api import TimeoutError as PWTimeout

from justpen_browser_mcp.errors import (
    ContextNotFoundError,
)


def make_page(mock_ctx_mgr, url="https://example.com", title="Example"):
    page = MagicMock()
    page.goto = AsyncMock()
    page.go_back = AsyncMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.wait_for_function = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()

    text_locator = MagicMock()
    text_locator.first = MagicMock()
    text_locator.first.wait_for = AsyncMock()
    page.get_by_text = MagicMock(return_value=text_locator)

    mock_ctx_mgr.active_page.return_value = page
    mock_ctx_mgr.get.return_value = MagicMock()
    # Default: no modals pending
    mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])
    mock_ctx_mgr.consume_modal_state = MagicMock(return_value=None)
    return page


class TestBrowserNavigate:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr, url="https://app.example.com/dashboard", title="Dashboard")
        result = await mcp_client.call_tool(
            "browser_navigate",
            {"context": "admin", "url": "https://app.example.com/dashboard"},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["url"] == "https://app.example.com/dashboard"
        assert result.data["data"]["title"] == "Dashboard"
        page.goto.assert_awaited_once_with("https://app.example.com/dashboard", wait_until="domcontentloaded")

    async def test_uses_two_phase_wait(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        await mcp_client.call_tool(
            "browser_navigate",
            {"context": "admin", "url": "https://example.com"},
        )
        page.goto.assert_awaited_once_with("https://example.com", wait_until="domcontentloaded")
        page.wait_for_load_state.assert_awaited_once_with("load", timeout=5000)

    async def test_url_normalization_localhost(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        await mcp_client.call_tool(
            "browser_navigate",
            {"context": "admin", "url": "localhost:3000"},
        )
        page.goto.assert_awaited_once_with("http://localhost:3000", wait_until="domcontentloaded")

    async def test_url_normalization_bare_hostname(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        await mcp_client.call_tool(
            "browser_navigate",
            {"context": "admin", "url": "example.com"},
        )
        page.goto.assert_awaited_once_with("https://example.com", wait_until="domcontentloaded")

    async def test_load_timeout_swallowed(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.wait_for_load_state = AsyncMock(side_effect=PWTimeout("slow"))
        result = await mcp_client.call_tool(
            "browser_navigate",
            {"context": "admin", "url": "https://example.com"},
        )
        assert result.data["status"] == "success"

    async def test_unknown_context(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.get.side_effect = ContextNotFoundError("missing")
        result = await mcp_client.call_tool(
            "browser_navigate",
            {"context": "admin", "url": "https://x.com"},
        )
        assert result.data["error_type"] == "context_not_found"


class TestBrowserNavigateBack:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_navigate_back", {"context": "admin"})
        assert result.data["status"] == "success"
        page.go_back.assert_awaited_once()

    async def test_modal_guard_blocks(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "alert"
        dialog.message = "oops"
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[{"kind": "dialog", "object": dialog, "page": page}])
        result = await mcp_client.call_tool("browser_navigate_back", {"context": "admin"})
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserWaitFor:
    async def test_text_visible(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_wait_for", {"context": "admin", "text": "Welcome"})
        assert result.data["status"] == "success"
        page.get_by_text.assert_called_once_with("Welcome")
        page.get_by_text.return_value.first.wait_for.assert_awaited_once_with(state="visible")

    async def test_text_gone(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_wait_for", {"context": "admin", "text_gone": "Loading"})
        assert result.data["status"] == "success"
        page.get_by_text.assert_called_once_with("Loading")
        page.get_by_text.return_value.first.wait_for.assert_awaited_once_with(state="hidden")

    async def test_time_in_seconds(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_wait_for", {"context": "admin", "time": 0.5})
        assert result.data["status"] == "success"
        page.wait_for_timeout.assert_awaited_once_with(500)

    async def test_time_capped_at_30s(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_wait_for", {"context": "admin", "time": 60})
        assert result.data["status"] == "success"
        page.wait_for_timeout.assert_awaited_once_with(30000)

    async def test_combination(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_wait_for",
            {"context": "admin", "text": "A", "time": 0.1},
        )
        assert result.data["status"] == "success"
        page.wait_for_timeout.assert_awaited_once_with(100)
        page.get_by_text.assert_called_once_with("A")

    async def test_neither_invalid(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_wait_for", {"context": "admin"})
        assert result.data["error_type"] == "invalid_params"
