"""Utility tools — 4 tools.

browser_resize, browser_pdf_save, browser_generate_locator, browser_tabs.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from playwright.async_api import BrowserContext

from ..errors import BrowserMcpError
from ..instance_manager import InstanceManager, InstanceState, assert_no_modal
from ..ref_resolver import resolve_selector_to_stable
from ..responses import error_response, success_response
from .navigation import canonicalize_browser_url

logger = logging.getLogger(__name__)


def _register_browser_resize(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_resize(instance: str, width: int, height: int) -> dict[str, Any]:
        """Resize the viewport of the active page to the given pixel dimensions.

        Affects only the active page; other tabs in the instance are unchanged.
        Changes take effect immediately. Use this to test responsive layouts or
        to ensure a particular viewport before taking a screenshot.

        Returns on success:
            data: {"width": int, "height": int}  — the dimensions that were applied

        Errors:
            instance_not_found — instance does not exist
        """
        try:
            mgr.get(instance)
            assert_no_modal(mgr, instance)
            async with mgr.lock_for(instance):
                page = await mgr.active_page(instance)
                await page.set_viewport_size({"width": width, "height": height})
            return success_response(instance, data={"width": width, "height": height})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_resize failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_pdf_save(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_pdf_save(
        instance: str,
        file_path: str | None = None,
        paper_format: str = "A4",
        *,
        landscape: bool = False,
        print_background: bool = False,
    ) -> dict[str, Any]:
        """Render the active page as a PDF and save it to the given file path.

        file_path is optional — when omitted, a file named ``page-{timestamp}.pdf``
        is written in the current working directory. paper_format is a paper
        size string: "A4" (default), "Letter", "A3", etc. landscape rotates the
        page to landscape orientation. print_background includes CSS
        backgrounds in the rendered output (off by default to match browser
        print behavior). Parent directories of file_path are created
        automatically if they don't exist. Only works in headless mode
        (Camoufox runs headless by default).

        Returns on success:
            data: {"saved_to": str, "size_bytes": int}

        Errors:
            instance_not_found  — instance does not exist
            modal_state_blocked — a dialog is pending and must be handled first
            internal_error      — PDF generation failed (e.g. not in headless mode)
        """
        try:
            mgr.get(instance)
            assert_no_modal(mgr, instance)
            async with mgr.lock_for(instance):
                page = await mgr.active_page(instance)
                pdf_bytes = await page.pdf(
                    format=paper_format,
                    landscape=landscape,
                    print_background=print_background,
                )
            if file_path is None:
                base = os.environ.get("JUSTPEN_WORKSPACE", "/workspace")
                file_path = f"{base}/output/evidence/page-{int(time.time())}.pdf"
            pdf_path = Path(file_path)
            await asyncio.to_thread(pdf_path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(pdf_path.write_bytes, pdf_bytes)
            return success_response(instance, data={"saved_to": file_path, "size_bytes": len(pdf_bytes)})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_pdf_save failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_generate_locator(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_generate_locator(
        instance: str,
        ref: str | None = None,
        selector: str | None = None,
        element: str | None = None,
    ) -> dict[str, Any]:
        """Generate a stable, durable Playwright locator for an element.

        The element can be identified in one of two ways (exactly one of
        `ref` or `selector` must be provided):

          - ref: an ephemeral snapshot ref (from browser_snapshot). The tool
            uses Playwright's resolveSelector protocol method to compute a
            stable locator — prioritized in this order: data-testid > ARIA
            role + name > label > placeholder > alt text > title > text
            content > CSS fallback. The result survives navigation and can
            be used to build durable test code or reusable workflow
            definitions (e.g. a saved login flow replayed in future
            sessions).
          - selector: a raw CSS selector. In this mode the selector is
            returned verbatim as both the internal and python form — no
            resolution to a more stable representation is performed. Use
            this when you already know the selector you want to store.

        `element` is an optional free-form human description of the element
        (for logging/permission-gating parity with the Microsoft Playwright
        MCP surface); it is currently unused by the implementation.

        Two representations are returned:
          - internal_selector: a Playwright selector string usable directly
            with page.locator(internal_selector). Durable at runtime.
          - python_syntax: a human-readable Python API call string like
            'get_by_role("button", name="Submit")' — for codegen output
            when saving a flow to a file.

        Returns on success:
            data: {
                "ref": str | None,         # the ref that was resolved, if any
                "selector": str | None,    # the selector that was passed through, if any
                "internal_selector": str,  # durable Playwright selector
                "python_syntax": str,      # Python API call syntax
            }

        Errors:
            instance_not_found  — call browser_create_instance first
            invalid_params      — neither or both of ref/selector supplied
            modal_state_blocked — a dialog is pending and must be handled first
            stale_ref           — ref is from an older snapshot; capture a new snapshot

        Usage notes:
          - The internal_selector form is exact (strict/case-sensitive for
            test IDs, case-insensitive for role names — matching Playwright's
            default behavior).
          - For elements with no accessible name (anonymous divs, etc.) the
            locator may fall back to CSS, which is less stable. Prefer to
            add data-testid attributes to such elements.
          - To save a durable workflow, call this tool right after each
            significant ref-based action and store the python_syntax strings;
            they can be replayed in a future session without any snapshots.
        """
        if (ref is None) == (selector is None):
            return error_response(
                instance,
                "invalid_params",
                "exactly one of 'ref' or 'selector' must be provided",
            )
        if element:
            logger.debug("browser_generate_locator: %s", element)
        try:
            mgr.get(instance)
            assert_no_modal(mgr, instance)
            async with mgr.lock_for(instance):
                page = await mgr.active_page(instance)
                if ref is not None:
                    result = await resolve_selector_to_stable(page, ref)
                else:
                    result = {
                        "internal_selector": selector,
                        "python_syntax": f"locator({selector!r})",
                    }
            return success_response(
                instance,
                data={
                    "ref": ref,
                    "selector": selector,
                    "internal_selector": result["internal_selector"],
                    "python_syntax": result["python_syntax"],
                },
            )
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_generate_locator failed")
            return error_response(instance, "internal_error", str(e))


async def _tabs_list(ctx: BrowserContext, instance: str) -> dict[str, Any]:
    tabs = [{"index": i, "url": p.url} for i, p in enumerate(ctx.pages)]
    return success_response(instance, data={"tabs": tabs})


async def _tabs_new(
    ctx: BrowserContext,
    instance: str,
    istate: InstanceState,
    url: str | None,
) -> dict[str, Any]:
    page = await ctx.new_page()
    if url:
        await page.goto(canonicalize_browser_url(url))
    istate.active_page_index = len(ctx.pages) - 1
    return success_response(instance, data={"index": len(ctx.pages) - 1, "url": page.url})


async def _tabs_close(
    ctx: BrowserContext,
    instance: str,
    istate: InstanceState,
    index: int | None,
) -> dict[str, Any]:
    if index is None or index < 0 or index >= len(ctx.pages):
        return error_response(instance, "invalid_params", f"invalid tab index: {index}")
    await ctx.pages[index].close()
    current_active = istate.active_page_index
    new_active = current_active - 1 if index < current_active else current_active
    remaining = len(ctx.pages)
    new_active = 0 if remaining == 0 else max(0, min(new_active, remaining - 1))
    istate.active_page_index = new_active
    return success_response(instance, data={"closed_index": index})


async def _tabs_select(
    ctx: BrowserContext,
    instance: str,
    mgr: InstanceManager,
    index: int | None,
) -> dict[str, Any]:
    if index is None or index < 0 or index >= len(ctx.pages):
        return error_response(instance, "invalid_params", f"invalid tab index: {index}")
    mgr.set_active_page(instance, index)
    selected = ctx.pages[index]
    await selected.bring_to_front()
    return success_response(instance, data={"selected_index": index})


def _register_browser_tabs(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_tabs(
        instance: str,
        action: str,
        index: int | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Manage tabs (pages) within a browser instance.

        action must be one of:
          "list"   — list all open tabs with their index and URL.
                     Returns: data: {"tabs": [{"index": int, "url": str}, ...]}
          "new"    — open a new tab, optionally navigating to url.
                     Returns: data: {"index": int, "url": str}
          "close"  — close the tab at the given index. index is required.
                     Returns: data: {"closed_index": int}
          "select" — bring the tab at the given index to the front, making it
                     the active page for subsequent tool calls. index is required.
                     Returns: data: {"selected_index": int}

        Errors:
            instance_not_found — instance does not exist
            invalid_params     — unrecognized action, or index missing/out of range
        """
        if action not in ("list", "new", "close", "select"):
            return error_response(
                instance,
                "invalid_params",
                f"action must be 'list'|'new'|'close'|'select', got {action!r}",
            )
        try:
            rec = mgr.get(instance)
            async with mgr.lock_for(instance):
                ctx = rec.context
                istate = mgr.state(instance)
                if action == "list":
                    return await _tabs_list(ctx, instance)
                if action == "new":
                    return await _tabs_new(ctx, instance, istate, url)
                if action == "close":
                    return await _tabs_close(ctx, instance, istate, index)
                return await _tabs_select(ctx, instance, mgr, index)
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_tabs failed")
            return error_response(instance, "internal_error", str(e))


def register(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register miscellaneous utility tools on the MCP server."""
    _register_browser_resize(mcp, mgr)
    _register_browser_pdf_save(mcp, mgr)
    _register_browser_generate_locator(mcp, mgr)
    _register_browser_tabs(mcp, mgr)
