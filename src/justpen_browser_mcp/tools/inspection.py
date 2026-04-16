"""Inspection tools — 4 tools.

browser_snapshot, browser_screenshot, browser_console_messages, browser_network_requests.

Console messages and network requests are collected by event listeners
attached at context creation time. The buffers live as private attributes
on the BrowserContext (set by ContextManager) so tools can read them
without their own state.
"""

import base64
import logging
import re
from io import BytesIO

from fastmcp import FastMCP

from ..context_manager import ContextManager, assert_no_modal
from ..errors import BrowserMcpError
from ..ref_resolver import capture_snapshot
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)

try:
    from PIL import Image as _PILImage
except ImportError:  # pragma: no cover - PIL is in deps but guarded anyway
    _PILImage = None  # type: ignore[assignment]


_VALID_CONSOLE_LEVELS = {"log", "info", "warning", "error", "debug"}
_STATIC_RESOURCE_TYPES = {"image", "font", "stylesheet", "media", "manifest"}
_CLAUDE_VISION_MAX_DIM = 1568


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_snapshot(context: str, selector: str | None = None) -> dict:
        """Capture an accessibility snapshot of the active page in LLM-friendly YAML.

        Default (selector=None): a full-page snapshot is captured via the internal
        snapshotForAI channel. Each interactive element is annotated with a
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
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file-chooser is pending
            internal_error       — snapshot call failed
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                if selector is None:
                    snapshot = await capture_snapshot(page)
                else:
                    locator = page.locator(selector)
                    snapshot = await locator.aria_snapshot(timeout=5000)
            return success_response(context, data={"snapshot": snapshot, "url": page.url})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_snapshot failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_screenshot(context: str, image_format: str = "png", *, full_page: bool = False) -> dict:
        """Take a visual screenshot of the active page and return it as base64.

        image_format must be "png" (default, lossless) or "jpeg" (lossy, smaller).
        full_page=False (default) captures only the current viewport;
        full_page=True captures the entire scrollable page.

        If PIL/Pillow is available, oversized images are automatically
        downscaled so the longest side is at most 1568px — Claude's current
        vision input limit. The width/height fields in the response reflect
        the FINAL (possibly downscaled) image dimensions.

        Returns on success:
            data: {"image_base64": str, "image_format": str,
                   "width": int | None, "height": int | None}
            — width/height are None only when PIL is unavailable.

        Errors:
            context_not_found    — context does not exist
            invalid_params       — image_format is not "png" or "jpeg"
            modal_state_blocked  — a dialog or file-chooser is pending

        Use browser_snapshot for most inspection tasks; screenshots are for
        visual debugging or when accessibility data is insufficient.
        """
        if image_format not in ("png", "jpeg"):
            return error_response(
                context,
                "invalid_params",
                f"image_format must be 'png' or 'jpeg', got {image_format!r}",
            )
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                image_bytes = await page.screenshot(type=image_format, full_page=full_page)

            width: int | None = None
            height: int | None = None
            if _PILImage is not None:
                try:
                    img = _PILImage.open(BytesIO(image_bytes))
                    img.load()
                    max_dim = max(img.width, img.height)
                    if max_dim > _CLAUDE_VISION_MAX_DIM:
                        scale = _CLAUDE_VISION_MAX_DIM / max_dim
                        new_size = (
                            max(1, int(img.width * scale)),
                            max(1, int(img.height * scale)),
                        )
                        img = img.resize(new_size, _PILImage.LANCZOS)
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

            return success_response(
                context,
                data={
                    "image_base64": base64.b64encode(image_bytes).decode("ascii"),
                    "image_format": image_format,
                    "width": width,
                    "height": height,
                },
            )
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_screenshot failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_console_messages(context: str, level: str | None = None) -> dict:
        """Return all console messages collected since the context was created.

        Messages are captured by an event listener attached at context creation.
        The buffer is cumulative — it includes ALL messages across ALL pages and
        ALL navigations in this context (not just since the last navigation).

        Each entry has {type, text, location} where location is "url:line:col"
        or None when unavailable. Uncaught page errors are also captured as
        entries with type="error" (and location=None).

        level (optional) filters by message type. Valid values:
        "log", "info", "warning", "error", "debug". None returns all messages.

        Returns on success:
            data: {"messages": [{"type": str, "text": str,
                                  "location": str | None}, ...]}

        Errors:
            context_not_found — context does not exist
            invalid_params    — level is not a recognised value

        Useful for debugging JavaScript errors or confirming page-side logging.
        """
        if level is not None and level not in _VALID_CONSOLE_LEVELS:
            return error_response(
                context,
                "invalid_params",
                f"level must be one of {sorted(_VALID_CONSOLE_LEVELS)}, got {level!r}",
            )
        try:
            ctx = await ctx_mgr.get(context)
            messages = list(getattr(ctx, "_console_messages", []))
            if level is not None:
                messages = [m for m in messages if m.get("type") == level]
            return success_response(context, data={"messages": messages})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_console_messages failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_network_requests(context: str, url_filter: str | None = None, *, static: bool = False) -> dict:
        """Return all network requests collected since the context was created.

        Requests are captured by an event listener attached at context creation.
        The buffer is cumulative — it includes ALL requests across ALL pages and
        ALL navigations in this context (not just since the last navigation).

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
            context_not_found — context does not exist
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
                    context,
                    "invalid_params",
                    f"url_filter is not a valid regular expression: {e}",
                )
        try:
            ctx = await ctx_mgr.get(context)
            requests = list(getattr(ctx, "_network_requests", []))
            if not static:
                requests = [r for r in requests if r.get("resource_type") not in _STATIC_RESOURCE_TYPES]
            if compiled is not None:
                requests = [r for r in requests if compiled.search(r.get("url", ""))]
            # Strip private bookkeeping keys (e.g. "_id" used by the
            # response listener to match by request identity) before
            # returning to the caller.
            requests = [{k: v for k, v in r.items() if not k.startswith("_")} for r in requests]
            return success_response(context, data={"requests": requests})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_network_requests failed")
            return error_response(context, "internal_error", str(e))
