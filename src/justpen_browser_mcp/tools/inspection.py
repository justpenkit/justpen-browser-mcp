"""Inspection tools — 4 tools.

browser_snapshot, browser_screenshot, browser_console_messages, browser_network_requests.

Console messages and network requests are collected by event listeners
attached at instance creation time. The buffers live on the InstanceState
so tools can read them without their own state.
"""

import base64
import json
import logging
import re
from io import BytesIO
from typing import Any

from anyio import Path as AsyncPath
from fastmcp import FastMCP

from ..errors import BrowserMcpError
from ..instance_manager import InstanceManager, assert_no_modal
from ..operation_context import mark_artifact_write_started, mark_operation_started
from ..ref_resolver import capture_snapshot
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)

try:
    from PIL import Image as _PILImage
except ImportError:  # pragma: no cover - PIL is in deps but guarded anyway
    _PILImage = None


_VALID_CONSOLE_LEVELS = {"log", "info", "warning", "error", "debug"}
_STATIC_RESOURCE_TYPES = {"image", "font", "stylesheet", "media", "manifest"}
_SCREENSHOT_MAX_DIM = 1568


async def _event_result(instance: str, field: str, result: dict[str, Any], path: str | None) -> dict[str, Any]:
    data = {**result, field: result["items"]}
    data.pop("items")
    if path is not None:
        mark_artifact_write_started()
        await AsyncPath(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        data["count"] = len(data.pop(field))
        data["path"] = path
    return success_response(instance, data=data)


def _register_browser_snapshot(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_snapshot(instance: str, selector: str | None = None) -> dict[str, Any]:
        """Capture an accessibility snapshot of the active page in LLM-friendly YAML.

        Default (selector=None): a full-page snapshot is captured via the internal
        Frame.ariaSnapshot channel with mode="ai". Each interactive element is annotated with a
        [ref=eN] tag, for example:
            button "Submit" [ref=e12]
            textbox "Email" [ref=e7]
        Pass the ref value to browser_click, browser_type, etc. to interact
        with that element. Refs are session-scoped and valid until the next
        navigation or page reload.

        Selector mode (selector!=None): calls Locator.aria_snapshot on the
        matching element and returns a plain aria YAML WITHOUT ref annotations.
        Use this for scoped inspection of a known subtree; use the default
        (no selector) mode when you need refs for subsequent interaction.

        Returns on success:
            data: {"snapshot": str, "url": str}
            — snapshot is a YAML string, url is the current page URL

        Errors:
            instance_not_found   — instance does not exist
            modal_state_blocked  — a dialog or file-chooser is pending
            internal_error       — snapshot call failed
        """
        try:
            mgr.get(instance)
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                page = await mgr.active_page(instance)
                if selector is None:
                    snapshot = await capture_snapshot(page)
                else:
                    locator = page.locator(selector)
                    snapshot = await locator.aria_snapshot(timeout=5000)
            return success_response(instance, data={"snapshot": snapshot, "url": page.url})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_snapshot failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_screenshot(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_screenshot(
        instance: str, image_format: str = "png", *, full_page: bool = False, path: str | None = None
    ) -> dict[str, Any]:
        """Take a visual screenshot of the active page and return it as base64.

        image_format must be "png" (default, lossless) or "jpeg" (lossy, smaller).
        full_page=False (default) captures only the current viewport;
        full_page=True captures the entire scrollable page.

        If PIL/Pillow is available, oversized images are automatically
        downscaled so the longest side is at most 1568px to bound image output.
        Pass path to save the final image on the server instead of returning base64.
        The width/height fields in the response reflect
        the FINAL (possibly downscaled) image dimensions.

        Returns on success:
            data: {"image_base64": str, "image_format": str,
                   "width": int | None, "height": int | None}
            — width/height are None only when PIL is unavailable.

        Errors:
            instance_not_found   — instance does not exist
            invalid_params       — image_format is not "png" or "jpeg"
            modal_state_blocked  — a dialog or file-chooser is pending

        Use browser_snapshot for most inspection tasks; screenshots are for
        visual debugging or when accessibility data is insufficient.
        """
        if image_format not in ("png", "jpeg"):
            return error_response(
                instance,
                "invalid_params",
                f"image_format must be 'png' or 'jpeg', got {image_format!r}",
            )
        try:
            mgr.get(instance)
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                page = await mgr.active_page(instance)
                image_bytes = await page.screenshot(type=image_format, full_page=full_page)

            width: int | None = None
            height: int | None = None
            if _PILImage is not None:
                try:
                    img = _PILImage.open(BytesIO(image_bytes))
                    img.load()
                    max_dim = max(img.width, img.height)
                    if max_dim > _SCREENSHOT_MAX_DIM:
                        scale = _SCREENSHOT_MAX_DIM / max_dim
                        new_size = (
                            max(1, int(img.width * scale)),
                            max(1, int(img.height * scale)),
                        )
                        img = img.resize(new_size, _PILImage.Resampling.LANCZOS)
                        buf = BytesIO()
                        save_format = "PNG" if image_format == "png" else "JPEG"
                        if save_format == "JPEG" and img.mode != "RGB":
                            img = img.convert("RGB")
                        img.save(buf, format=save_format)
                        image_bytes = buf.getvalue()
                    width, height = img.width, img.height
                except Exception:
                    logger.exception("browser_screenshot: PIL processing failed")
                    width = None
                    height = None

            data: dict[str, Any] = {"image_format": image_format, "width": width, "height": height}
            if path is None:
                data["image_base64"] = base64.b64encode(image_bytes).decode("ascii")
            else:
                mark_artifact_write_started()
                await AsyncPath(path).write_bytes(image_bytes)
                data["path"] = path
            return success_response(instance, data=data)
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_screenshot failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_console_messages(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_console_messages(
        instance: str,
        level: str | None = None,
        *,
        after: str | None = None,
        limit: int = 100,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Read a bounded page of recent console messages across instance pages.

        Messages are captured by an event listener attached at instance creation.
        The buffer evicts old records at the configured capacity. Use next_cursor
        as after with the same filters; limit must be 1-500. dropped_count and
        retention_lost disclose missing history. Entries include sequence,
        timestamp, page_id, and truncated_fields when large text was shortened.
        Pass path to write this JSON page on the server; the result then contains
        path/count and pagination metadata instead of inline messages.

        Each entry has {type, text, location} where location is "url:line:col"
        or None when unavailable. Uncaught page errors are also captured as
        entries with type="error" (and location=None).

        level (optional) filters by message type. Valid values:
        "log", "info", "warning", "error", "debug". None returns all messages.

        Returns on success:
            data: {"messages": [{"type": str, "text": str,
                                  "location": str | None}, ...]}

        Errors:
            instance_not_found — instance does not exist
            invalid_params    — level is not a recognised value

        Useful for debugging JavaScript errors or confirming page-side logging.
        """
        if level is not None and level not in _VALID_CONSOLE_LEVELS:
            return error_response(
                instance,
                "invalid_params",
                f"level must be one of {sorted(_VALID_CONSOLE_LEVELS)}, got {level!r}",
            )
        try:
            record = mgr.get(instance)
            mark_operation_started(record.instance_id)
            result = mgr.state(instance).console_messages.page(
                after=after,
                limit=limit,
                predicate=lambda entry: level is None or entry.get("type") == level,
            )
            return await _event_result(instance, "messages", result, path)
        except ValueError as e:
            return error_response(instance, "invalid_params", str(e))
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_console_messages failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_network_requests(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_network_requests(
        instance: str,
        url_filter: str | None = None,
        *,
        static: bool = False,
        after: str | None = None,
        limit: int = 100,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Read a bounded page of recent network request states across instance pages.

        Requests are captured by an event listener attached at instance creation.
        Old records are evicted at the configured capacity. Use next_cursor as
        after with the same filters; limit must be 1-500. dropped_count and
        retention_lost disclose missing history. A response/failure update has a
        new sequence but the same request_id, so incremental consumers should
        upsert by request_id. Entries also include timestamp and page_id.
        Pass path to export this JSON page on the server and return path/count
        plus pagination metadata instead of inline requests.

        Each entry has {url, method, status, resource_type, failure}:
        - status is None until the response arrives (or if it never does).
        - resource_type is always populated (e.g. "fetch", "image", "document").
        - failure is populated with Playwright's failure string when the
          request errors out; None on success or while still pending.

        static (default False): when False, entries whose resource_type is
        image/font/stylesheet/media/manifest are filtered out (typical page
        asset noise). Pass static=True to include everything.

        url_filter (optional): a Python regular expression. When provided, only
        requests whose URL matches are returned. Applied AFTER the static
        filter. An invalid regex returns invalid_params.

        Returns on success:
            data: {"requests": [{"url": str, "method": str,
                                  "status": int | None,
                                  "resource_type": str,
                                  "failure": str | None}, ...]}

        Errors:
            instance_not_found — instance does not exist
            invalid_params    — url_filter is not a valid regular expression

        Useful for verifying API calls were made, checking redirect chains,
        or diagnosing network errors during page load.
        """
        compiled = None
        if url_filter is not None:
            try:
                compiled = re.compile(url_filter)
            except re.error as e:
                return error_response(
                    instance,
                    "invalid_params",
                    f"url_filter is not a valid regular expression: {e}",
                )
        try:
            record = mgr.get(instance)
            mark_operation_started(record.instance_id)

            def matches(entry: dict[str, Any]) -> bool:
                return (static or entry.get("resource_type") not in _STATIC_RESOURCE_TYPES) and (
                    compiled is None or compiled.search(entry.get("url", "")) is not None
                )

            result = mgr.state(instance).network_requests.page(after=after, limit=limit, predicate=matches)
            return await _event_result(instance, "requests", result, path)
        except ValueError as e:
            return error_response(instance, "invalid_params", str(e))
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_network_requests failed")
            return error_response(instance, "internal_error", str(e))


def register(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register page inspection tools on the MCP server."""
    _register_browser_snapshot(mcp, mgr)
    _register_browser_screenshot(mcp, mgr)
    _register_browser_console_messages(mcp, mgr)
    _register_browser_network_requests(mcp, mgr)
