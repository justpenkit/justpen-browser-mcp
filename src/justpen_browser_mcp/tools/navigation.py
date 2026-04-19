"""Navigation tools — 3 tools.

browser_navigate, browser_navigate_back, browser_wait_for.
"""

import contextlib
import logging
from typing import Any

from fastmcp import FastMCP
from playwright.async_api import Error as PlaywrightError, TimeoutError as PWTimeout

from ..context_manager import ContextManager, assert_no_modal
from ..errors import (
    BrowserMcpError,
    NavigationFailedError,
    NavigationTimeoutError,
    WaitTimeoutError,
)
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)


def _looks_like_ip(host: str) -> bool:
    """Return True if *host* is a bare IPv4 address (with optional port)."""
    # Strip port suffix if present.
    bare = host.split(":", maxsplit=1)[0]
    parts = bare.split(".")
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


def normalize_url(url: str) -> str:
    """Normalize a user-supplied URL.

    - Bare "localhost" / "localhost:PORT" → http://localhost[:PORT]
    - Bare IPv4 address (e.g. "10.0.0.5:8080") → http://IP[:PORT]
    - Schemeless hostname containing "." → https://hostname
    - Otherwise unchanged.
    """
    if "://" in url:
        return url
    if url == "localhost" or url.startswith(("localhost:", "localhost/")):
        return f"http://{url}"
    # Bare IP addresses default to http://, not https://.
    # Strip path, query, and fragment before checking.
    host_part = url.split("/", maxsplit=1)[0].split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if _looks_like_ip(host_part):
        return f"http://{url}"
    if "." in url:
        return f"https://{url}"
    return url


def _register_browser_navigate(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_navigate(context: str, url: str) -> dict[str, Any]:
        """Navigate the active page in the given context to a URL.

        This navigates the CURRENT active page. Other tabs in the context
        are untouched. To navigate a different tab, select it first via
        browser_tabs(action='select', index=N).

        URL normalization: bare hostnames like "example.com" are upgraded to
        "https://example.com"; "localhost[:PORT]" is upgraded to "http://".

        The page is considered loaded when DOMContentLoaded fires; we then
        wait up to 5 additional seconds for the full "load" event but do
        not fail if it doesn't arrive (matches Microsoft's playwright-mcp).

        Returns on success:
            data: {"url": str, "title": str}
            — final URL after any redirects, page title after load

        Errors:
            context_not_found    — call browser_create_context first
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            navigation_failed    — network error, invalid URL, or page crash
            navigation_timeout   — page did not finish loading in time

        After a successful navigation, previous refs from browser_snapshot
        are invalidated. Take a fresh snapshot before referencing elements.
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            normalized = normalize_url(url)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                try:
                    await page.goto(normalized, wait_until="domcontentloaded")
                except PWTimeout as e:
                    raise NavigationTimeoutError(str(e)) from e
                except PlaywrightError as e:
                    err_msg = str(e).lower()
                    if "net::err_aborted" in err_msg or "download" in err_msg:
                        # Navigation aborted because a download started.
                        # This is expected for export/report/download
                        # endpoints — not a real navigation failure.
                        return success_response(
                            context,
                            data={
                                "url": page.url,
                                "title": await page.title(),
                                "download": True,
                            },
                        )
                    raise NavigationFailedError(str(e)) from e
                with contextlib.suppress(PWTimeout):
                    await page.wait_for_load_state("load", timeout=5000)
                return success_response(
                    context,
                    data={"url": page.url, "title": await page.title()},
                )
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_navigate failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_navigate_back(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_navigate_back(context: str) -> dict[str, Any]:
        """Navigate back one step in the browser history for the active page.

        Equivalent to pressing the browser Back button. Has no effect if there
        is no history entry to go back to (the page stays where it is).

        Returns on success:
            data: {"url": str}  — URL of the page after going back

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            navigation_failed    — Playwright error during back navigation
            navigation_timeout   — navigation did not complete in time

        After a successful navigation, previous refs from browser_snapshot
        are invalidated. Take a fresh snapshot before referencing elements.
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                try:
                    await page.go_back()
                except PWTimeout as e:
                    raise NavigationTimeoutError(str(e)) from e
                except PlaywrightError as e:
                    raise NavigationFailedError(str(e)) from e
                return success_response(context, data={"url": page.url})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_navigate_back failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_wait_for(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_wait_for(
        context: str,
        text: str | None = None,
        text_gone: str | None = None,
        time: float | None = None,
    ) -> dict[str, Any]:
        """Wait for text to appear, text to disappear, or a fixed duration.

        At least one of text/text_gone/time must be provided. Combinations are
        allowed; conditions are evaluated in order: time → text_gone → text
        (matching Microsoft's playwright-mcp).

        time: seconds to wait unconditionally (capped at 30 seconds).
        text_gone: waits until the given string is hidden on the active page.
        text: waits until the given string is visible on the active page.

        Returns on success:
            data: {"waited_for": str}  — description of the conditions waited on

        Errors:
            context_not_found   — context does not exist
            modal_state_blocked — a dialog or file-chooser is pending; resolve it first
            invalid_params      — none of text/text_gone/time were provided
            wait_timeout        — text did not appear/disappear in the default timeout
        """
        if text is None and text_gone is None and time is None:
            return error_response(
                context,
                "invalid_params",
                "At least one of 'text', 'text_gone', or 'time' must be provided.",
            )
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                parts: list[str] = []
                if time is not None:
                    capped_seconds = min(30.0, float(time))
                    await page.wait_for_timeout(int(capped_seconds * 1000))
                    parts.append(f"{capped_seconds}s")
                if text_gone is not None:
                    try:
                        await page.get_by_text(text_gone).first.wait_for(state="hidden")
                    except PWTimeout as e:
                        raise WaitTimeoutError(f"Text '{text_gone}' did not disappear: {e}") from e
                    parts.append(f"text_gone={text_gone!r}")
                if text is not None:
                    try:
                        await page.get_by_text(text).first.wait_for(state="visible")
                    except PWTimeout as e:
                        raise WaitTimeoutError(f"Text '{text}' did not appear: {e}") from e
                    parts.append(f"text={text!r}")
                return success_response(context, data={"waited_for": ", ".join(parts)})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_wait_for failed")
            return error_response(context, "internal_error", str(e))


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:
    _register_browser_navigate(mcp, ctx_mgr)
    _register_browser_navigate_back(mcp, ctx_mgr)
    _register_browser_wait_for(mcp, ctx_mgr)
