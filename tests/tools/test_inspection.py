"""Tests for tools/inspection.py — 4 inspection tools."""

import base64
import json
from contextlib import asynccontextmanager
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anyio import Path as AsyncPath
from PIL import Image

from justpen_browser_mcp.events import EventBuffer

pytestmark = pytest.mark.integration


def _events(entries):
    result = EventBuffer()
    for entry in entries:
        result.append(entry)
    return result


def make_page(mock_ctx_mgr):
    page = MagicMock()
    page.aria_snapshot = AsyncMock(return_value="- button [ref=e1]: Submit")
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n")
    page.url = "https://example.com"
    # Locator used for selector-mode snapshots
    locator = MagicMock()
    locator.aria_snapshot = AsyncMock(return_value="- heading: Main")
    page.locator = MagicMock(return_value=locator)

    mock_ctx_mgr.active_page.return_value = page
    mock_ctx_mgr.get.return_value = MagicMock()
    # Default: no modals pending
    mock_ctx_mgr.get_modal_states = MagicMock(return_value=[])
    mock_ctx_mgr.consume_modal_state = MagicMock(return_value=None)
    return page


def _pil_png_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestBrowserSnapshot:
    async def test_no_selector_uses_capture_snapshot(self, mcp_client, mock_ctx_mgr):
        make_page(mock_ctx_mgr)
        with patch(
            "justpen_browser_mcp.tools.inspection.capture_snapshot",
            return_value="- button [ref=e1]: Submit",
        ):
            result = await mcp_client.call_tool("browser_snapshot", {"instance": "admin"})
        assert result.data["status"] == "success"
        assert "[ref=e1]" in result.data["data"]["snapshot"]
        assert result.data["data"]["url"] == "https://example.com"

    async def test_with_selector_calls_locator_aria_snapshot(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        with patch("justpen_browser_mcp.tools.inspection.capture_snapshot") as cap:
            result = await mcp_client.call_tool("browser_snapshot", {"instance": "admin", "selector": "#main"})
        page.locator.assert_called_once_with("#main")
        page.locator.return_value.aria_snapshot.assert_awaited_once_with(timeout=5000)
        cap.assert_not_called()
        assert result.data["status"] == "success"
        assert result.data["data"]["snapshot"] == "- heading: Main"

    async def test_modal_guard(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "confirm"
        dialog.message = "Sure?"
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[{"kind": "dialog", "object": dialog, "page": page}])
        result = await mcp_client.call_tool("browser_snapshot", {"instance": "admin"})
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserScreenshot:
    async def test_returns_base64_png(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.screenshot = AsyncMock(return_value=_pil_png_bytes(100, 50))
        result = await mcp_client.call_tool("browser_screenshot", {"instance": "admin"})
        assert result.data["status"] == "success"
        decoded = base64.b64decode(result.data["data"]["image_base64"])
        assert decoded.startswith(b"\x89PNG")
        assert result.data["data"]["image_format"] == "png"

    async def test_jpeg_format(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        img = Image.new("RGB", (100, 50), color=(0, 0, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        page.screenshot = AsyncMock(return_value=buf.getvalue())
        result = await mcp_client.call_tool("browser_screenshot", {"instance": "admin", "image_format": "jpeg"})
        page.screenshot.assert_awaited_once_with(type="jpeg", full_page=False)
        assert result.data["data"]["image_format"] == "jpeg"

    async def test_full_page_param_passed(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.screenshot = AsyncMock(return_value=_pil_png_bytes(100, 50))
        await mcp_client.call_tool("browser_screenshot", {"instance": "admin", "full_page": True})
        page.screenshot.assert_awaited_once_with(type="png", full_page=True)

    async def test_response_includes_dimensions(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.screenshot = AsyncMock(return_value=_pil_png_bytes(100, 50))
        result = await mcp_client.call_tool("browser_screenshot", {"instance": "admin"})
        assert result.data["data"]["width"] == 100
        assert result.data["data"]["height"] == 50

    async def test_downscaling_when_oversized(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.screenshot = AsyncMock(return_value=_pil_png_bytes(2000, 1000))
        result = await mcp_client.call_tool("browser_screenshot", {"instance": "admin"})
        w = result.data["data"]["width"]
        h = result.data["data"]["height"]
        assert w <= 1568
        assert h <= 1568
        assert max(w, h) == 1568
        # Decoded bytes should be a valid PNG that actually matches the width
        decoded = base64.b64decode(result.data["data"]["image_base64"])
        img = Image.open(BytesIO(decoded))
        assert img.width == w
        assert img.height == h

    async def test_modal_guard(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        dialog = MagicMock()
        dialog.type = "alert"
        dialog.message = "!"
        mock_ctx_mgr.get_modal_states = MagicMock(return_value=[{"kind": "dialog", "object": dialog, "page": page}])
        result = await mcp_client.call_tool("browser_screenshot", {"instance": "admin"})
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserConsoleMessages:
    async def test_returns_collected_messages(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.console_messages = _events(
            [
                {"type": "log", "text": "hello", "location": None},
                {"type": "error", "text": "boom", "location": "app.js:1:2"},
            ]
        )
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_console_messages", {"instance": "admin"})
        assert result.data["status"] == "success"
        assert len(result.data["data"]["messages"]) == 2

    async def test_level_filter(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.console_messages = _events(
            [
                {"type": "log", "text": "a", "location": None},
                {"type": "error", "text": "b", "location": None},
                {"type": "warning", "text": "c", "location": None},
            ]
        )
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_console_messages", {"instance": "admin", "level": "error"})
        assert result.data["status"] == "success"
        messages = result.data["data"]["messages"]
        assert len(messages) == 1
        assert messages[0]["type"] == "error"

    async def test_invalid_level(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.console_messages = _events([])
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_console_messages", {"instance": "admin", "level": "bogus"})
        assert result.data["error_type"] == "invalid_params"

    async def test_no_filter_returns_all(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.console_messages = _events(
            [
                {"type": "log", "text": "a", "location": None},
                {"type": "error", "text": "b", "location": None},
            ]
        )
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_console_messages", {"instance": "admin"})
        assert len(result.data["data"]["messages"]) == 2


class TestBrowserNetworkRequests:
    async def test_returns_collected_requests(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.network_requests = _events(
            [
                {
                    "url": "https://x.com/api",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "fetch",
                    "failure": None,
                },
            ]
        )
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_network_requests", {"instance": "admin"})
        assert result.data["status"] == "success"
        assert len(result.data["data"]["requests"]) == 1

    async def test_static_filter_default(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.network_requests = _events(
            [
                {
                    "url": "https://x.com/logo.png",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "image",
                    "failure": None,
                },
                {
                    "url": "https://x.com/api/users",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "fetch",
                    "failure": None,
                },
            ]
        )
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_network_requests", {"instance": "admin"})
        reqs = result.data["data"]["requests"]
        assert len(reqs) == 1
        assert reqs[0]["resource_type"] == "fetch"

    async def test_static_true_returns_all(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.network_requests = _events(
            [
                {
                    "url": "https://x.com/logo.png",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "image",
                    "failure": None,
                },
                {
                    "url": "https://x.com/api/users",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "fetch",
                    "failure": None,
                },
            ]
        )
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_network_requests", {"instance": "admin", "static": True})
        reqs = result.data["data"]["requests"]
        assert len(reqs) == 2

    async def test_url_regex_filter(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.network_requests = _events(
            [
                {
                    "url": "https://x.com/api/users",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "fetch",
                    "failure": None,
                },
                {
                    "url": "https://x.com/api/posts",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "fetch",
                    "failure": None,
                },
            ]
        )
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool(
            "browser_network_requests",
            {"instance": "admin", "url_filter": "api/users"},
        )
        reqs = result.data["data"]["requests"]
        assert len(reqs) == 1
        assert "api/users" in reqs[0]["url"]

    async def test_invalid_regex(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.network_requests = _events([])
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_network_requests", {"instance": "admin", "url_filter": "["})
        assert result.data["error_type"] == "invalid_params"

    async def test_network_requests_strips_internal_id(self, mcp_client, mock_ctx_mgr):
        mock_ctx_mgr.state.return_value.network_requests = _events(
            [
                {
                    "_id": 12345,
                    "url": "https://x.com/api",
                    "method": "GET",
                    "status": 200,
                    "resource_type": "fetch",
                    "failure": None,
                }
            ]
        )
        mock_ctx_mgr.get.return_value = MagicMock()
        result = await mcp_client.call_tool("browser_network_requests", {"instance": "admin"})
        reqs = result.data["data"]["requests"]
        assert len(reqs) == 1
        assert "_id" not in reqs[0]
        assert reqs[0]["url"] == "https://x.com/api"
        assert reqs[0]["status"] == 200


@pytest.mark.parametrize(
    ("tool", "field", "buffer_field"),
    [
        ("browser_console_messages", "messages", "console_messages"),
        ("browser_network_requests", "requests", "network_requests"),
    ],
)
async def test_event_queries_page_and_export_evidence(mcp_client, mock_ctx_mgr, tmp_path, tool, field, buffer_field):
    events = _events([{"text": str(number), "url": f"https://example.test/{number}"} for number in range(3)])
    setattr(mock_ctx_mgr.state.return_value, buffer_field, events)
    first = await mcp_client.call_tool(tool, {"instance": "admin", "limit": 1})
    assert first.data["status"] == "success"
    data = first.data["data"]
    assert len(data[field]) == 1
    assert data["has_more"] is True
    path = str(tmp_path / "events.json")
    second = await mcp_client.call_tool(tool, {"instance": "admin", "after": data["next_cursor"], "path": path})
    assert second.data["status"] == "success"
    assert second.data["data"]["path"] == path
    assert field not in second.data["data"]
    exported = json.loads(await AsyncPath(path).read_text())
    assert [entry["text"] for entry in exported[field]] == ["1", "2"]
    assert exported["has_more"] is False


@pytest.mark.parametrize("tool", ["browser_console_messages", "browser_network_requests"])
async def test_invalid_event_cursor_is_invalid_params(mcp_client, mock_ctx_mgr, tool):
    mock_ctx_mgr.state.return_value.console_messages = EventBuffer()
    mock_ctx_mgr.state.return_value.network_requests = EventBuffer()
    result = await mcp_client.call_tool(tool, {"instance": "admin", "after": "wrong-stream:1"})
    assert result.data["error_type"] == "invalid_params"


@pytest.mark.parametrize("tool", ["browser_snapshot", "browser_screenshot"])
async def test_inspection_modal_guard_runs_after_lock_wait(mcp_client, mock_ctx_mgr, tool):
    page = make_page(mock_ctx_mgr)
    dialog = MagicMock(type="alert", message="arrived during wait")

    @asynccontextmanager
    async def lock():
        mock_ctx_mgr.get_modal_states.return_value = [{"kind": "dialog", "page": page, "object": dialog}]
        yield

    mock_ctx_mgr.lock_for.side_effect = lambda instance: lock()
    result = await mcp_client.call_tool(tool, {"instance": "admin"})
    assert result.data["error_type"] == "modal_state_blocked"
    page.screenshot.assert_not_awaited()


async def test_screenshot_can_write_artifact_without_inline_image(mcp_client, mock_ctx_mgr, tmp_path):
    page = make_page(mock_ctx_mgr)
    expected = _pil_png_bytes(100, 50)
    page.screenshot = AsyncMock(return_value=expected)
    path = str(tmp_path / "screen.png")
    result = await mcp_client.call_tool("browser_screenshot", {"instance": "admin", "path": path})
    assert result.data["status"] == "success"
    assert result.data["data"]["path"] == path
    assert "image_base64" not in result.data["data"]
    assert await AsyncPath(path).read_bytes() == expected
