"""Tests for tools/inspection.py — 4 inspection tools."""

import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image


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
            result = await mcp_client.call_tool("browser_snapshot", {"context": "admin"})
        assert result.data["status"] == "success"
        assert "[ref=e1]" in result.data["data"]["snapshot"]
        assert result.data["data"]["url"] == "https://example.com"

    async def test_with_selector_calls_locator_aria_snapshot(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        with patch("justpen_browser_mcp.tools.inspection.capture_snapshot") as cap:
            result = await mcp_client.call_tool("browser_snapshot", {"context": "admin", "selector": "#main"})
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
        result = await mcp_client.call_tool("browser_snapshot", {"context": "admin"})
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserScreenshot:
    async def test_returns_base64_png(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.screenshot = AsyncMock(return_value=_pil_png_bytes(100, 50))
        result = await mcp_client.call_tool("browser_screenshot", {"context": "admin"})
        assert result.data["status"] == "success"
        decoded = base64.b64decode(result.data["data"]["image_base64"])
        assert decoded.startswith(b"\x89PNG")
        assert result.data["data"]["format"] == "png"

    async def test_jpeg_format(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        img = Image.new("RGB", (100, 50), color=(0, 0, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        page.screenshot = AsyncMock(return_value=buf.getvalue())
        result = await mcp_client.call_tool("browser_screenshot", {"context": "admin", "format": "jpeg"})
        page.screenshot.assert_awaited_once_with(type="jpeg", full_page=False)
        assert result.data["data"]["format"] == "jpeg"

    async def test_full_page_param_passed(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.screenshot = AsyncMock(return_value=_pil_png_bytes(100, 50))
        await mcp_client.call_tool("browser_screenshot", {"context": "admin", "full_page": True})
        page.screenshot.assert_awaited_once_with(type="png", full_page=True)

    async def test_response_includes_dimensions(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.screenshot = AsyncMock(return_value=_pil_png_bytes(100, 50))
        result = await mcp_client.call_tool("browser_screenshot", {"context": "admin"})
        assert result.data["data"]["width"] == 100
        assert result.data["data"]["height"] == 50

    async def test_downscaling_when_oversized(self, mcp_client, mock_ctx_mgr):
        page = make_page(mock_ctx_mgr)
        page.screenshot = AsyncMock(return_value=_pil_png_bytes(2000, 1000))
        result = await mcp_client.call_tool("browser_screenshot", {"context": "admin"})
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
        result = await mcp_client.call_tool("browser_screenshot", {"context": "admin"})
        assert result.data["error_type"] == "modal_state_blocked"


class TestBrowserConsoleMessages:
    async def test_returns_collected_messages(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._console_messages = [
            {"type": "log", "text": "hello", "location": None},
            {"type": "error", "text": "boom", "location": "app.js:1:2"},
        ]
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_console_messages", {"context": "admin"})
        assert result.data["status"] == "success"
        assert len(result.data["data"]["messages"]) == 2

    async def test_level_filter(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._console_messages = [
            {"type": "log", "text": "a", "location": None},
            {"type": "error", "text": "b", "location": None},
            {"type": "warning", "text": "c", "location": None},
        ]
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_console_messages", {"context": "admin", "level": "error"})
        assert result.data["status"] == "success"
        messages = result.data["data"]["messages"]
        assert len(messages) == 1
        assert messages[0]["type"] == "error"

    async def test_invalid_level(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._console_messages = []
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_console_messages", {"context": "admin", "level": "bogus"})
        assert result.data["error_type"] == "invalid_params"

    async def test_no_filter_returns_all(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._console_messages = [
            {"type": "log", "text": "a", "location": None},
            {"type": "error", "text": "b", "location": None},
        ]
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_console_messages", {"context": "admin"})
        assert len(result.data["data"]["messages"]) == 2


class TestBrowserNetworkRequests:
    async def test_returns_collected_requests(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._network_requests = [
            {
                "url": "https://x.com/api",
                "method": "GET",
                "status": 200,
                "resource_type": "fetch",
                "failure": None,
            },
        ]
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_network_requests", {"context": "admin"})
        assert result.data["status"] == "success"
        assert len(result.data["data"]["requests"]) == 1

    async def test_static_filter_default(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._network_requests = [
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
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_network_requests", {"context": "admin"})
        reqs = result.data["data"]["requests"]
        assert len(reqs) == 1
        assert reqs[0]["resource_type"] == "fetch"

    async def test_static_true_returns_all(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._network_requests = [
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
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_network_requests", {"context": "admin", "static": True})
        reqs = result.data["data"]["requests"]
        assert len(reqs) == 2

    async def test_url_regex_filter(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._network_requests = [
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
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool(
            "browser_network_requests",
            {"context": "admin", "filter": "api/users"},
        )
        reqs = result.data["data"]["requests"]
        assert len(reqs) == 1
        assert "api/users" in reqs[0]["url"]

    async def test_invalid_regex(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._network_requests = []
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_network_requests", {"context": "admin", "filter": "["})
        assert result.data["error_type"] == "invalid_params"

    async def test_network_requests_strips_internal_id(self, mcp_client, mock_ctx_mgr):
        ctx = MagicMock()
        ctx._network_requests = [
            {
                "_id": 12345,
                "url": "https://x.com/api",
                "method": "GET",
                "status": 200,
                "resource_type": "fetch",
                "failure": None,
            }
        ]
        mock_ctx_mgr.get.return_value = ctx
        result = await mcp_client.call_tool("browser_network_requests", {"context": "admin"})
        reqs = result.data["data"]["requests"]
        assert len(reqs) == 1
        assert "_id" not in reqs[0]
        assert reqs[0]["url"] == "https://x.com/api"
        assert reqs[0]["status"] == 200
