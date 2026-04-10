"""Tests for justpen_browser_mcp.ref_resolver."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import Error as PlaywrightError

from justpen_browser_mcp.ref_resolver import (
    capture_snapshot,
    locator_for_ref,
    resolve_ref,
)
from justpen_browser_mcp.errors import StaleRefError


class TestCaptureSnapshot:
    async def test_calls_snapshot_for_ai_via_channel(self):
        """capture_snapshot must call page._impl_obj._channel.send("snapshotForAI", ...)"""
        page = MagicMock()
        channel = MagicMock()
        channel.send = AsyncMock(return_value="- button [ref=e1]")
        page._impl_obj = MagicMock()
        page._impl_obj._channel = channel

        result = await capture_snapshot(page)
        assert result == "- button [ref=e1]"

        channel.send.assert_awaited_once()
        call_args = channel.send.call_args
        assert call_args[0][0] == "snapshotForAI"
        # Third positional arg is the params dict with timeout
        assert "timeout" in call_args[0][2]


class TestLocatorForRef:
    def test_constructs_aria_ref_locator(self):
        page = MagicMock()
        fake_locator = MagicMock()
        page.locator.return_value = fake_locator
        result = locator_for_ref(page, "e2")
        page.locator.assert_called_once_with("aria-ref=e2")
        assert result is fake_locator


class TestResolveRef:
    async def test_returns_locator_when_attached(self):
        page = MagicMock()
        fake_locator = MagicMock()
        fake_locator.wait_for = AsyncMock()
        page.locator.return_value = fake_locator
        result = await resolve_ref(page, "e2")
        assert result is fake_locator
        fake_locator.wait_for.assert_awaited_once_with(state="attached", timeout=1000)

    async def test_aria_ref_error_becomes_stale_ref(self):
        page = MagicMock()
        fake_locator = MagicMock()
        fake_locator.wait_for = AsyncMock(
            side_effect=PlaywrightError("aria-ref=e2 selector resolved to no element")
        )
        page.locator.return_value = fake_locator
        with pytest.raises(StaleRefError, match="not found in current page snapshot"):
            await resolve_ref(page, "e2")

    async def test_other_playwright_error_passes_through(self):
        page = MagicMock()
        fake_locator = MagicMock()
        fake_locator.wait_for = AsyncMock(
            side_effect=PlaywrightError("connection lost")
        )
        page.locator.return_value = fake_locator
        with pytest.raises(PlaywrightError, match="connection lost"):
            await resolve_ref(page, "e2")


class TestInternalToPython:
    def test_testid(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        assert (
            _internal_to_python('internal:testid=[data-testid="submit-btn"s]')
            == "get_by_test_id('submit-btn')"
        )

    def test_role_with_name(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        assert (
            _internal_to_python('internal:role=button[name="Cancel"i]')
            == "get_by_role(\"button\", name='Cancel')"
        )

    def test_role_with_exact_name(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        assert (
            _internal_to_python('internal:role=link[name="Home"s]')
            == "get_by_role(\"link\", name='Home', exact=True)"
        )

    def test_role_without_name(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        assert _internal_to_python("internal:role=img") == 'get_by_role("img")'

    def test_label(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        assert (
            _internal_to_python('internal:label="Password"s')
            == "get_by_label('Password', exact=True)"
        )

    def test_placeholder(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        assert (
            _internal_to_python('internal:attr=[placeholder="Email"i]')
            == "get_by_placeholder('Email')"
        )

    def test_text(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        assert _internal_to_python('internal:text="Hello"i') == "get_by_text('Hello')"

    def test_css_fallback(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        assert _internal_to_python("div.class > span") == "locator('div.class > span')"

    def test_role_with_escaped_quotes(self):
        """Internal selector contains \\\" to represent a literal double quote
        inside the name. Output must be valid Python literal syntax."""
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        result = _internal_to_python(r'internal:role=button[name="He said \"Go\""i]')
        assert result == 'get_by_role("button", name=\'He said "Go"\')'

    def test_label_with_escaped_quotes(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        result = _internal_to_python(r'internal:label="say \"hi\""s')
        assert result == "get_by_label('say \"hi\"', exact=True)"

    def test_testid_with_escaped_quotes(self):
        from justpen_browser_mcp.ref_resolver import _internal_to_python

        result = _internal_to_python(r'internal:testid=[data-testid="a\"b"s]')
        assert result == "get_by_test_id('a\"b')"


class TestResolveSelectorToStable:
    async def test_happy_path(self):
        from unittest.mock import AsyncMock, MagicMock
        from justpen_browser_mcp.ref_resolver import (
            resolve_selector_to_stable,
        )

        page = MagicMock()
        channel = MagicMock()
        channel.send = AsyncMock(return_value='internal:role=button[name="Submit"i]')
        page._impl_obj = MagicMock()
        page._impl_obj.main_frame = MagicMock()
        page._impl_obj.main_frame._channel = channel

        result = await resolve_selector_to_stable(page, "e2")
        assert result["internal_selector"] == 'internal:role=button[name="Submit"i]'
        assert result["python_syntax"] == "get_by_role(\"button\", name='Submit')"

        channel.send.assert_awaited_once()
        call = channel.send.call_args[0]
        assert call[0] == "resolveSelector"
        assert call[2] == {"selector": "aria-ref=e2"}

    async def test_stale_ref(self):
        from unittest.mock import AsyncMock, MagicMock
        from playwright.async_api import Error as PlaywrightError
        from justpen_browser_mcp.ref_resolver import (
            resolve_selector_to_stable,
        )
        from justpen_browser_mcp.errors import StaleRefError
        import pytest

        page = MagicMock()
        channel = MagicMock()
        channel.send = AsyncMock(
            side_effect=PlaywrightError("No element matching aria-ref=e99")
        )
        page._impl_obj = MagicMock()
        page._impl_obj.main_frame = MagicMock()
        page._impl_obj.main_frame._channel = channel

        with pytest.raises(StaleRefError):
            await resolve_selector_to_stable(page, "e99")
