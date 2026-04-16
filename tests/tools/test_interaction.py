"""Tests for tools/interaction.py — 9 interaction tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp.exceptions import ToolError

from justpen_browser_mcp.errors import (
    StaleRefError,
)


def make_page_with_locator(mock_ctx_mgr):
    locator = MagicMock()
    locator.click = AsyncMock()
    locator.dblclick = AsyncMock()
    locator.fill = AsyncMock()
    locator.type = AsyncMock()
    locator.press = AsyncMock()
    locator.hover = AsyncMock()
    locator.select_option = AsyncMock()
    locator.set_input_files = AsyncMock()
    locator.set_checked = AsyncMock()
    locator.drag_to = AsyncMock()
    locator.wait_for = AsyncMock()
    locator.text_content = AsyncMock(return_value="text")

    page = MagicMock()
    page.locator = MagicMock(return_value=locator)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.on = MagicMock()
    page.remove_all_listeners = MagicMock()
    page.wait_for_load_state = AsyncMock()

    mock_ctx_mgr.active_page.return_value = page
    mock_ctx_mgr.get.return_value = MagicMock()
    # Default: no modals pending
    mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])
    mock_ctx_mgr.consume_modal_state = MagicMock(return_value=None)
    return page, locator


class TestBrowserClick:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_click", {"context": "admin", "ref": "e2"})
        assert result.data["status"] == "success"
        page.locator.assert_called_with("aria-ref=e2")
        locator.click.assert_awaited_once_with(button="left")

    async def test_double_click_calls_dblclick(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_click",
            {"context": "admin", "ref": "e2", "double_click": True},
        )
        assert result.data["status"] == "success"
        locator.dblclick.assert_awaited_once_with(button="left")
        locator.click.assert_not_awaited()

    async def test_button_right(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_click",
            {"context": "admin", "ref": "e2", "button": "right"},
        )
        assert result.data["status"] == "success"
        locator.click.assert_awaited_once_with(button="right")

    async def test_modifiers(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_click",
            {"context": "admin", "ref": "e2", "modifiers": ["Shift", "Control"]},
        )
        assert result.data["status"] == "success"
        locator.click.assert_awaited_once_with(button="left", modifiers=["Shift", "Control"])

    async def test_invalid_button(self, mcp_client, mock_ctx_mgr):
        make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_click",
            {"context": "admin", "ref": "e2", "button": "frobnicate"},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_invalid_modifier(self, mcp_client, mock_ctx_mgr):
        make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_click",
            {"context": "admin", "ref": "e2", "modifiers": ["Hyper"]},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_stale_ref(self, mcp_client, mock_ctx_mgr):
        make_page_with_locator(mock_ctx_mgr)
        with patch(
            "justpen_browser_mcp.tools.interaction.resolve_ref",
            side_effect=StaleRefError("ref e2 not found"),
        ):
            result = await mcp_client.call_tool("browser_click", {"context": "admin", "ref": "e2"})
        assert result.data["error_type"] == "stale_ref"

    async def test_blocked_by_modal(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "confirm"
        dialog.message = "Are you sure?"
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[{"kind": "dialog", "object": dialog, "page": page}])
        result = await mcp_client.call_tool("browser_click", {"context": "admin", "ref": "e2"})
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserType:
    async def test_clear_first_default(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_type",
            {"context": "admin", "ref": "e3", "text": "hello"},
        )
        assert result.data["status"] == "success"
        locator.fill.assert_awaited_once_with("hello")

    async def test_no_clear_first_uses_type(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_type",
            {"context": "admin", "ref": "e3", "text": "x", "clear_first": False},
        )
        assert result.data["status"] == "success"
        locator.type.assert_awaited_once_with("x")

    async def test_submit_presses_enter(self, mcp_client, mock_ctx_mgr):
        page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_type",
            {"context": "admin", "ref": "e3", "text": "hi", "submit": True},
        )
        assert result.data["status"] == "success"
        locator.fill.assert_awaited_once_with("hi")
        locator.press.assert_awaited_once_with("Enter")
        page.wait_for_load_state.assert_awaited()


class TestBrowserFillForm:
    async def test_fills_each_field_textbox_default(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [
                    {"ref": "e1", "value": "user@x.com"},
                    {"ref": "e2", "value": "pass"},
                ],
            },
        )
        assert result.data["status"] == "success"
        assert locator.fill.await_count == 2

    async def test_routes_by_type(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [
                    {"ref": "e1", "value": "hello", "type": "textbox"},
                    {"ref": "e2", "value": True, "type": "checkbox"},
                    {"ref": "e3", "value": True, "type": "radio"},
                    {"ref": "e4", "value": "blue", "type": "combobox"},
                ],
            },
        )
        assert result.data["status"] == "success"
        locator.fill.assert_awaited_once_with("hello")
        assert locator.set_checked.await_count == 2
        locator.select_option.assert_awaited_once_with("blue")

    async def test_fill_form_missing_ref_invalid(self, mcp_client, mock_ctx_mgr):
        make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"type": "textbox", "value": "x"}],
            },
        )
        assert result.data["error_type"] == "invalid_params"
        assert "ref" in result.data["message"]

    async def test_fill_form_missing_value_invalid(self, mcp_client, mock_ctx_mgr):
        make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"ref": "e1"}],
            },
        )
        assert result.data["error_type"] == "invalid_params"
        assert "value" in result.data["message"]

    async def test_fill_form_field_not_dict_invalid(self, mcp_client, mock_ctx_mgr):
        """Non-dict field entries should be rejected as invalid params.

        FastMCP's pydantic schema validation rejects the call before our
        tool body runs, which surfaces as a ToolError — that is the
        MCP-level equivalent of invalid_params and is strictly better than
        an internal_error.
        """
        make_page_with_locator(mock_ctx_mgr)
        with pytest.raises(ToolError, match="valid dictionary|dict_type"):
            await mcp_client.call_tool(
                "browser_fill_form",
                {
                    "context": "admin",
                    "fields": ["oops"],
                },
            )

    async def test_unknown_type_returns_invalid_params(self, mcp_client, mock_ctx_mgr):
        make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"ref": "e1", "value": "x", "type": "frobnicate"}],
            },
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_blocked_by_modal(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        fc = MagicMock()
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[{"kind": "filechooser", "object": fc, "page": page}])
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {"context": "admin", "fields": [{"ref": "e1", "value": "x"}]},
        )
        assert result.data["error_type"] == "modal_state_blocked"

    async def test_fill_form_checkbox_string_false_unchecks(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"ref": "e1", "value": "false", "type": "checkbox"}],
            },
        )
        assert result.data["status"] == "success"
        locator.set_checked.assert_awaited_once_with(False)

    async def test_fill_form_checkbox_string_zero_unchecks(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"ref": "e1", "value": "0", "type": "checkbox"}],
            },
        )
        assert result.data["status"] == "success"
        locator.set_checked.assert_awaited_once_with(False)

    async def test_fill_form_checkbox_string_true_checks(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"ref": "e1", "value": "true", "type": "checkbox"}],
            },
        )
        assert result.data["status"] == "success"
        locator.set_checked.assert_awaited_once_with(True)

    async def test_fill_form_checkbox_real_bool(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"ref": "e1", "value": False, "type": "checkbox"}],
            },
        )
        assert result.data["status"] == "success"
        locator.set_checked.assert_awaited_once_with(False)

    async def test_fill_form_checkbox_invalid_value(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"ref": "e1", "value": "bogus", "type": "checkbox"}],
            },
        )
        assert result.data["error_type"] == "invalid_params"
        locator.set_checked.assert_not_awaited()

    async def test_fill_form_radio_string_false_unchecks(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_fill_form",
            {
                "context": "admin",
                "fields": [{"ref": "e1", "value": "false", "type": "radio"}],
            },
        )
        assert result.data["status"] == "success"
        locator.set_checked.assert_awaited_once_with(False)


class TestBrowserSelectOption:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_select_option",
            {"context": "admin", "ref": "e4", "value": "blue"},
        )
        assert result.data["status"] == "success"
        locator.select_option.assert_awaited_once_with("blue")

    async def test_list_value(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_select_option",
            {"context": "admin", "ref": "e4", "value": ["red", "green"]},
        )
        assert result.data["status"] == "success"
        locator.select_option.assert_awaited_once_with(["red", "green"])
        assert result.data["data"]["selected"] == ["red", "green"]


class TestBrowserHover:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_hover", {"context": "admin", "ref": "e5"})
        assert result.data["status"] == "success"
        locator.hover.assert_awaited_once()


class TestBrowserDrag:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        _page, locator = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_drag",
            {"context": "admin", "source_ref": "e1", "target_ref": "e2"},
        )
        assert result.data["status"] == "success"
        locator.drag_to.assert_awaited_once()


class TestBrowserPressKey:
    async def test_success(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_press_key", {"context": "admin", "key": "Tab"})
        assert result.data["status"] == "success"
        page.keyboard.press.assert_awaited_once_with("Tab")
        page.wait_for_load_state.assert_not_awaited()

    async def test_enter_waits_for_load_state(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        result = await mcp_client.call_tool("browser_press_key", {"context": "admin", "key": "Enter"})
        assert result.data["status"] == "success"
        page.keyboard.press.assert_awaited_once_with("Enter")
        page.wait_for_load_state.assert_awaited_once_with("domcontentloaded", timeout=2000)


class TestBrowserFileUpload:
    async def test_consumes_pending_filechooser(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        file_chooser = MagicMock()
        file_chooser.set_files = AsyncMock()
        mock_ctx_mgr.consume_modal_state = MagicMock(
            return_value={"kind": "filechooser", "object": file_chooser, "page": page}
        )
        result = await mcp_client.call_tool(
            "browser_file_upload",
            {"context": "admin", "paths": ["/tmp/a.txt", "/tmp/b.txt"]},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["uploaded_count"] == 2
        file_chooser.set_files.assert_awaited_once_with(["/tmp/a.txt", "/tmp/b.txt"])

    async def test_no_pending_filechooser(self, mcp_client, mock_ctx_mgr):
        make_page_with_locator(mock_ctx_mgr)
        mock_ctx_mgr.consume_modal_state = MagicMock(return_value=None)
        result = await mcp_client.call_tool(
            "browser_file_upload",
            {"context": "admin", "paths": ["/tmp/a.txt"]},
        )
        assert result.data["error_type"] == "modal_state_blocked"

    async def test_cancel_with_no_paths(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        file_chooser = MagicMock()
        file_chooser.set_files = AsyncMock()
        mock_ctx_mgr.consume_modal_state = MagicMock(
            return_value={"kind": "filechooser", "object": file_chooser, "page": page}
        )
        result = await mcp_client.call_tool(
            "browser_file_upload",
            {"context": "admin"},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["cancelled"] is True
        file_chooser.set_files.assert_not_awaited()


class TestBrowserHandleDialog:
    async def test_accept_consumes_dialog(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "confirm"
        dialog.message = "Are you sure?"
        dialog.accept = AsyncMock()
        dialog.dismiss = AsyncMock()
        mock_ctx_mgr.consume_modal_state = MagicMock(return_value={"kind": "dialog", "object": dialog, "page": page})
        result = await mcp_client.call_tool(
            "browser_handle_dialog",
            {"context": "admin", "accept": True},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["action"] == "accepted"
        assert result.data["data"]["dialog_type"] == "confirm"
        assert result.data["data"]["message"] == "Are you sure?"
        dialog.accept.assert_awaited_once_with("")
        dialog.dismiss.assert_not_awaited()

    async def test_dismiss_consumes_dialog(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "alert"
        dialog.message = "Hi"
        dialog.accept = AsyncMock()
        dialog.dismiss = AsyncMock()
        mock_ctx_mgr.consume_modal_state = MagicMock(return_value={"kind": "dialog", "object": dialog, "page": page})
        result = await mcp_client.call_tool(
            "browser_handle_dialog",
            {"context": "admin", "accept": False},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["action"] == "dismissed"
        dialog.dismiss.assert_awaited_once()

    async def test_accept_with_prompt_text(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page_with_locator(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "prompt"
        dialog.message = "Name?"
        dialog.accept = AsyncMock()
        mock_ctx_mgr.consume_modal_state = MagicMock(return_value={"kind": "dialog", "object": dialog, "page": page})
        result = await mcp_client.call_tool(
            "browser_handle_dialog",
            {"context": "admin", "accept": True, "prompt_text": "Alice"},
        )
        assert result.data["status"] == "success"
        dialog.accept.assert_awaited_once_with("Alice")

    async def test_no_pending_dialog(self, mcp_client, mock_ctx_mgr):
        make_page_with_locator(mock_ctx_mgr)
        mock_ctx_mgr.consume_modal_state = MagicMock(return_value=None)
        result = await mcp_client.call_tool(
            "browser_handle_dialog",
            {"context": "admin", "accept": True},
        )
        assert result.data["error_type"] == "modal_state_blocked"
