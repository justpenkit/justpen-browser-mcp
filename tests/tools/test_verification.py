"""Tests for tools/verification.py — 4 verification tools."""

from unittest.mock import AsyncMock, MagicMock, patch

from justpen_browser_mcp.errors import StaleRefError


def make_page(
    mock_ctx_mgr,
    *,
    visible=True,
    text_present=True,
    value="actual",
    checked=False,
):
    locator = MagicMock()
    locator.is_visible = AsyncMock(return_value=visible)
    locator.input_value = AsyncMock(return_value=value)
    locator.is_checked = AsyncMock(return_value=checked)
    locator.wait_for = AsyncMock()

    page = MagicMock()
    page.locator = MagicMock(return_value=locator)

    # Main-frame get_by_text returns a locator whose .first.is_visible() returns text_present.
    main_text_first = MagicMock()
    main_text_first.is_visible = AsyncMock(return_value=text_present)
    main_text_locator = MagicMock()
    main_text_locator.first = main_text_first

    main_frame = MagicMock(name="main_frame")
    main_frame.get_by_text = MagicMock(return_value=main_text_locator)
    page.main_frame = main_frame
    page.frames = [main_frame]

    # Also expose page.get_by_text for any direct callers.
    page.get_by_text = MagicMock(return_value=main_text_locator)

    mock_ctx_mgr.active_page.return_value = page
    mock_ctx_mgr.get.return_value = MagicMock()
    mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])
    mock_ctx_mgr.consume_modal_state = MagicMock(return_value=None)
    return page, locator


def pending_dialog_states(page):
    dialog = MagicMock()
    dialog.type = "alert"
    dialog.message = "oops"
    return [{"kind": "dialog", "object": dialog, "page": page}]


class TestBrowserVerifyElementVisible:
    async def test_visible(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr, visible=True)
        result = await mcp_client.call_tool(
            "browser_verify_element_visible",
            {"context": "admin", "ref": "e1"},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["visible"] is True

    async def test_not_visible(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr, visible=False)
        result = await mcp_client.call_tool(
            "browser_verify_element_visible",
            {"context": "admin", "ref": "e1"},
        )
        assert result.data["error_type"] == "verification_failed"

    async def test_iframe_resolution_falls_back(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page(mock_ctx_mgr, visible=True)

        # Build an iframe locator that is_visible()==True.
        iframe_locator = MagicMock()
        iframe_locator.wait_for = AsyncMock()
        iframe_locator.is_visible = AsyncMock(return_value=True)

        child_frame = MagicMock(name="child_frame")
        child_frame.locator = MagicMock(return_value=iframe_locator)

        page.main_frame = page.main_frame  # keep existing
        page.frames = [page.main_frame, child_frame]

        with patch(
            "justpen_browser_mcp.tools.verification.resolve_ref",
            AsyncMock(side_effect=StaleRefError("not in main")),
        ):
            result = await mcp_client.call_tool(
                "browser_verify_element_visible",
                {"context": "admin", "ref": "e1"},
            )
        assert result.data["status"] == "success"
        child_frame.locator.assert_called_once_with("aria-ref=e1")

    async def test_modal_guard(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page(mock_ctx_mgr)
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=pending_dialog_states(page))
        result = await mcp_client.call_tool(
            "browser_verify_element_visible",
            {"context": "admin", "ref": "e1"},
        )
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserVerifyListVisible:
    async def test_refs_mode_unchanged(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr, visible=True)
        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {"context": "admin", "refs": ["e1", "e2", "e3"]},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["visible_refs"] == ["e1", "e2", "e3"]

    async def test_one_missing(self, mcp_client, mock_ctx_mgr):
        locator = MagicMock()
        locator.is_visible = AsyncMock(side_effect=[True, False, True])
        locator.wait_for = AsyncMock()
        page = MagicMock()
        page.locator = MagicMock(return_value=locator)
        page.main_frame = MagicMock()
        page.frames = [page.main_frame]
        mock_ctx_mgr.active_page.return_value = page
        mock_ctx_mgr.get.return_value = MagicMock()
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])

        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {"context": "admin", "refs": ["e1", "e2", "e3"]},
        )
        assert result.data["error_type"] == "verification_failed"

    async def test_container_mode(self, mcp_client, mock_ctx_mgr):
        _page, container_locator = make_page(mock_ctx_mgr, visible=True)

        # container_locator.get_by_text(item).first.is_visible() → True for both.
        inner_first = MagicMock()
        inner_first.is_visible = AsyncMock(return_value=True)
        inner_locator = MagicMock()
        inner_locator.first = inner_first
        container_locator.get_by_text = MagicMock(return_value=inner_locator)

        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {
                "context": "admin",
                "container_ref": "e3",
                "items": ["foo", "bar"],
            },
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["container_ref"] == "e3"
        assert result.data["data"]["verified_items"] == ["foo", "bar"]
        # Called once for "foo" and once for "bar".
        assert container_locator.get_by_text.call_count == 2

    async def test_container_mode_missing_item(self, mcp_client, mock_ctx_mgr):
        _page, container_locator = make_page(mock_ctx_mgr, visible=True)

        # First item is visible, second isn't.
        first_a = MagicMock()
        first_a.is_visible = AsyncMock(return_value=True)
        loc_a = MagicMock()
        loc_a.first = first_a
        first_b = MagicMock()
        first_b.is_visible = AsyncMock(return_value=False)
        loc_b = MagicMock()
        loc_b.first = first_b
        container_locator.get_by_text = MagicMock(side_effect=[loc_a, loc_b])

        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {
                "context": "admin",
                "container_ref": "e3",
                "items": ["foo", "bar"],
            },
        )
        assert result.data["error_type"] == "verification_failed"

    async def test_container_missing_items_param(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {"context": "admin", "container_ref": "e3"},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_mutually_exclusive(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {
                "context": "admin",
                "refs": ["e1"],
                "container_ref": "e2",
                "items": ["foo"],
            },
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_neither_mode(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {"context": "admin"},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_verify_list_empty_refs_invalid(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {"context": "admin", "refs": []},
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_verify_list_empty_items_invalid(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_verify_list_visible",
            {"context": "admin", "container_ref": "e1", "items": []},
        )
        assert result.data["error_type"] == "invalid_params"


class TestBrowserVerifyTextVisible:
    async def test_present(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr, text_present=True)
        result = await mcp_client.call_tool(
            "browser_verify_text_visible",
            {"context": "admin", "text": "Welcome"},
        )
        assert result.data["status"] == "success"

    async def test_absent(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr, text_present=False)
        result = await mcp_client.call_tool(
            "browser_verify_text_visible",
            {"context": "admin", "text": "Welcome"},
        )
        assert result.data["error_type"] == "verification_failed"

    async def test_text_in_iframe(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page(mock_ctx_mgr, text_present=False)

        # Main frame returns False; child frame returns True.
        child_first = MagicMock()
        child_first.is_visible = AsyncMock(return_value=True)
        child_text_locator = MagicMock()
        child_text_locator.first = child_first
        child_frame = MagicMock(name="child_frame")
        child_frame.get_by_text = MagicMock(return_value=child_text_locator)

        page.frames = [page.main_frame, child_frame]

        result = await mcp_client.call_tool(
            "browser_verify_text_visible",
            {"context": "admin", "text": "Welcome"},
        )
        assert result.data["status"] == "success"
        child_frame.get_by_text.assert_called_once_with("Welcome")

    async def test_uses_first_for_strict_mode(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page(mock_ctx_mgr, text_present=True)
        await mcp_client.call_tool(
            "browser_verify_text_visible",
            {"context": "admin", "text": "Welcome"},
        )
        # Confirm we accessed .first on the get_by_text result.
        main_text_locator = page.main_frame.get_by_text.return_value
        # Access to .first attribute on MagicMock records as a child mock.
        assert main_text_locator.first.is_visible.await_count == 1

    async def test_modal_guard(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page(mock_ctx_mgr)
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=pending_dialog_states(page))
        result = await mcp_client.call_tool(
            "browser_verify_text_visible",
            {"context": "admin", "text": "Welcome"},
        )
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserVerifyValue:
    async def test_text_default_unchanged(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr, value="hello")
        result = await mcp_client.call_tool(
            "browser_verify_value",
            {"context": "admin", "ref": "e1", "expected_value": "hello"},
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["value"] == "hello"
        assert result.data["data"]["element_type"] == "text"

    async def test_text_mismatch(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr, value="actual")
        result = await mcp_client.call_tool(
            "browser_verify_value",
            {"context": "admin", "ref": "e1", "expected_value": "expected"},
        )
        assert result.data["error_type"] == "verification_failed"

    async def test_checkbox_true(self, mcp_client, mock_ctx_mgr):
        _, locator = make_page(mock_ctx_mgr, checked=True)
        result = await mcp_client.call_tool(
            "browser_verify_value",
            {
                "context": "admin",
                "ref": "e1",
                "expected_value": "true",
                "element_type": "checkbox",
            },
        )
        assert result.data["status"] == "success"
        assert result.data["data"]["value"] is True
        assert result.data["data"]["element_type"] == "checkbox"
        locator.is_checked.assert_awaited_once()
        # Should NOT have called input_value.
        locator.input_value.assert_not_called()

    async def test_checkbox_false_mismatch(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr, checked=False)
        result = await mcp_client.call_tool(
            "browser_verify_value",
            {
                "context": "admin",
                "ref": "e1",
                "expected_value": "true",
                "element_type": "checkbox",
            },
        )
        assert result.data["error_type"] == "verification_failed"

    async def test_radio_true(self, mcp_client, mock_ctx_mgr):
        _, locator = make_page(mock_ctx_mgr, checked=True)
        result = await mcp_client.call_tool(
            "browser_verify_value",
            {
                "context": "admin",
                "ref": "e1",
                "expected_value": "1",
                "element_type": "radio",
            },
        )
        assert result.data["status"] == "success"
        locator.is_checked.assert_awaited_once()

    async def test_invalid_element_type(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        result = await mcp_client.call_tool(
            "browser_verify_value",
            {
                "context": "admin",
                "ref": "e1",
                "expected_value": "true",
                "element_type": "bogus",
            },
        )
        assert result.data["error_type"] == "invalid_params"

    async def test_modal_guard(self, mcp_client, mock_ctx_mgr):
        page, _ = make_page(mock_ctx_mgr, value="hello")
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=pending_dialog_states(page))
        result = await mcp_client.call_tool(
            "browser_verify_value",
            {"context": "admin", "ref": "e1", "expected_value": "hello"},
        )
        assert result.data["error_type"] == "modal_state_blocked"
