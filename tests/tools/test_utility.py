"""Tests for tools/utility.py — 3 utility tools."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from justpen_browser_mcp.errors import ContextNotFoundError, StaleRefError


def make_page(mock_ctx_mgr):
    page = MagicMock()
    page.set_viewport_size = AsyncMock()
    page.pdf = AsyncMock(return_value=b"%PDF-1.4")
    locator = MagicMock()
    locator.text_content = AsyncMock(return_value="Submit")
    locator.wait_for = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    mock_ctx_mgr.active_page.return_value = page
    new_page_mock = MagicMock(
        close=AsyncMock(),
        goto=AsyncMock(),
        bring_to_front=AsyncMock(),
        url="https://x.com",
    )
    ctx = MagicMock()
    ctx.pages = [page]
    ctx.new_page = AsyncMock(return_value=new_page_mock)
    mock_ctx_mgr.get.return_value = ctx
    # Default: no modals pending
    mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])
    mock_ctx_mgr.consume_modal_state = MagicMock(return_value=None)
    return page


class TestBrowserResize:
    async def test_resize(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_resize",
            {"context": "admin", "width": 1280, "height": 800},
        )
        assert result.data["status"] == "success"
        page.set_viewport_size.assert_awaited_once_with({"width": 1280, "height": 800})


class TestBrowserPdfSave:
    async def test_saves_pdf(self, mcp_client, mock_ctx_mgr, tmp_path):
        make_page(mock_ctx_mgr)
        out = tmp_path / "out.pdf"
        result = await mcp_client.call_tool(
            "browser_pdf_save",
            {"context": "admin", "file_path": str(out)},
        )
        assert result.data["status"] == "success"
        assert out.exists()
        assert out.read_bytes().startswith(b"%PDF")

    async def test_pdf_save_default_filename(self, mcp_client, mock_ctx_mgr, tmp_path, monkeypatch):
        make_page(mock_ctx_mgr)
        monkeypatch.setenv("JUSTPEN_WORKSPACE", str(tmp_path))
        result = await mcp_client.call_tool("browser_pdf_save", {"context": "admin"})
        assert result.data["status"] == "success"
        saved = result.data["data"]["saved_to"]
        assert "output/evidence/page-" in saved
        assert await asyncio.to_thread(Path(saved).exists)

    async def test_pdf_save_landscape(self, mcp_client, mock_ctx_mgr, tmp_path):
        page = make_page(mock_ctx_mgr)
        out = tmp_path / "land.pdf"
        result = await mcp_client.call_tool(
            "browser_pdf_save",
            {"context": "admin", "file_path": str(out), "landscape": True},
        )
        assert result.data["status"] == "success"
        page.pdf.assert_awaited_once()
        kwargs = page.pdf.call_args.kwargs
        assert kwargs.get("landscape") is True

    async def test_pdf_save_print_background(self, mcp_client, mock_ctx_mgr, tmp_path):
        page = make_page(mock_ctx_mgr)
        out = tmp_path / "bg.pdf"
        result = await mcp_client.call_tool(
            "browser_pdf_save",
            {
                "context": "admin",
                "file_path": str(out),
                "print_background": True,
            },
        )
        assert result.data["status"] == "success"
        kwargs = page.pdf.call_args.kwargs
        assert kwargs.get("print_background") is True


class TestBrowserResizeModalGuard:
    async def test_resize_modal_guard(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "alert"
        dialog.message = "hi"
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[{"kind": "dialog", "object": dialog, "page": page}])
        result = await mcp_client.call_tool(
            "browser_resize",
            {"context": "admin", "width": 800, "height": 600},
        )
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserTabs:
    async def test_list_tabs(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_tabs", {"context": "admin", "action": "list"})
        assert result.data["status"] == "success"
        assert "tabs" in result.data["data"]

    async def test_new_tab(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_tabs",
            {"context": "admin", "action": "new", "url": "https://x.com"},
        )
        assert result.data["status"] == "success"

    async def test_tabs_select_updates_active_index(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        page0 = MagicMock(bring_to_front=AsyncMock(), url="https://a")
        page1 = MagicMock(bring_to_front=AsyncMock(), url="https://b")
        ctx = MagicMock()
        ctx.pages = [page0, page1]
        mock_ctx_mgr.state.return_value.active_page_index = 0
        mock_ctx_mgr.get.return_value = ctx
        mock_ctx_mgr.set_active_page = MagicMock()

        result = await mcp_client.call_tool(
            "browser_tabs",
            {"context": "admin", "action": "select", "index": 1},
        )
        assert result.data["status"] == "success"
        mock_ctx_mgr.set_active_page.assert_called_once_with("admin", 1)
        page1.bring_to_front.assert_awaited_once()

    async def test_tabs_close_active_resets_index(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        page0 = MagicMock(close=AsyncMock())
        page1 = MagicMock(close=AsyncMock())
        pages = [page0, page1]

        async def close_page1():
            pages.remove(page1)

        page1.close.side_effect = close_page1
        ctx = MagicMock()
        ctx.pages = pages
        mock_ctx_mgr.state.return_value.active_page_index = 1
        mock_ctx_mgr.get.return_value = ctx

        result = await mcp_client.call_tool(
            "browser_tabs",
            {"context": "admin", "action": "close", "index": 1},
        )
        assert result.data["status"] == "success"
        assert mock_ctx_mgr.state.return_value.active_page_index == 0

    async def test_tabs_close_lower_decrements(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        page0 = MagicMock(close=AsyncMock())
        page1 = MagicMock(close=AsyncMock())
        page2 = MagicMock(close=AsyncMock())
        pages = [page0, page1, page2]

        async def close_page0():
            pages.remove(page0)

        page0.close.side_effect = close_page0
        ctx = MagicMock()
        ctx.pages = pages
        mock_ctx_mgr.state.return_value.active_page_index = 2
        mock_ctx_mgr.get.return_value = ctx

        result = await mcp_client.call_tool(
            "browser_tabs",
            {"context": "admin", "action": "close", "index": 0},
        )
        assert result.data["status"] == "success"
        assert mock_ctx_mgr.state.return_value.active_page_index == 1

    async def test_tabs_close_negative_index_invalid(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        ctx = MagicMock()
        ctx.pages = [MagicMock(close=AsyncMock())]
        mock_ctx_mgr.state.return_value.active_page_index = 0
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool(
            "browser_tabs",
            {"context": "admin", "action": "close", "index": -1},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_tabs_select_negative_index_invalid(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        ctx = MagicMock()
        ctx.pages = [MagicMock(bring_to_front=AsyncMock())]
        mock_ctx_mgr.state.return_value.active_page_index = 0
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool(
            "browser_tabs",
            {"context": "admin", "action": "select", "index": -1},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_tabs_new_sets_active_to_new_tab(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        initial_page = MagicMock(url="https://a")
        pages = [initial_page]
        new_page_obj = MagicMock(
            close=AsyncMock(),
            goto=AsyncMock(),
            url="https://new.example",
        )

        async def add_page(*args, **kwargs):
            pages.append(new_page_obj)
            return new_page_obj

        ctx = MagicMock()
        ctx.pages = pages
        mock_ctx_mgr.state.return_value.active_page_index = 0
        ctx.new_page = AsyncMock(side_effect=add_page)
        mock_ctx_mgr.get.return_value = ctx

        result = await mcp_client.call_tool(
            "browser_tabs",
            {"context": "admin", "action": "new", "url": "https://new.example"},
        )
        assert result.data["status"] == "success"
        assert mock_ctx_mgr.state.return_value.active_page_index == 1


class TestBrowserGenerateLocator:
    async def test_success_testid(self, mcp_client, mock_ctx_mgr):
        page = MagicMock()
        mock_ctx_mgr.active_page.return_value = page
        mock_ctx_mgr.get.return_value = MagicMock()
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])

        with patch(
            "justpen_browser_mcp.tools.utility.resolve_selector_to_stable",
            new=AsyncMock(
                return_value={
                    "internal_selector": 'internal:testid=[data-testid="login-btn"s]',
                    "python_syntax": 'get_by_test_id("login-btn")',
                }
            ),
        ):
            result = await mcp_client.call_tool(
                "browser_generate_locator",
                {"context": "admin", "ref": "e5"},
            )

        assert result.data["status"] == "success"
        assert result.data["data"]["ref"] == "e5"
        assert result.data["data"]["internal_selector"] == 'internal:testid=[data-testid="login-btn"s]'
        assert result.data["data"]["python_syntax"] == 'get_by_test_id("login-btn")'

    async def test_stale_ref(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.active_page.return_value = MagicMock()
        mock_ctx_mgr.get.return_value = MagicMock()
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])

        with patch(
            "justpen_browser_mcp.tools.utility.resolve_selector_to_stable",
            new=AsyncMock(side_effect=StaleRefError("ref e99 not found")),
        ):
            result = await mcp_client.call_tool(
                "browser_generate_locator",
                {"context": "admin", "ref": "e99"},
            )

        assert result.data["status"] == "error"
        assert result.data["error_type"] == "stale_ref"

    async def test_unknown_context(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.get.side_effect = ContextNotFoundError("missing")

        result = await mcp_client.call_tool(
            "browser_generate_locator",
            {"context": "admin", "ref": "e1"},
        )
        assert result.data["error_type"] == "context_not_found"

    async def test_generate_locator_selector_mode(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_generate_locator",
            {"context": "admin", "selector": "#main"},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["internal_selector"] == "#main"
        assert result.data["data"]["python_syntax"] == "locator('#main')"
        assert result.data["data"]["selector"] == "#main"
        assert result.data["data"]["ref"] is None

    async def test_generate_locator_both_invalid(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_generate_locator",
            {"context": "admin", "ref": "e1", "selector": "#x"},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_generate_locator_neither_invalid(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_generate_locator",
            {"context": "admin"},
        )
        assert result.data["error_type"] == "invalid_params"
