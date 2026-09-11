"""Utility tools — 4 tools.

browser_resize, browser_pdf_save, browser_generate_locator, browser_tabs.
"""

import contextlib
import logging
from typing import Any

import anyio
from fastmcp import FastMCP
from playwright.async_api import BrowserContext

from ..errors import BrowserMcpError
from ..instance_manager import InstanceManager, assert_no_modal
from ..operation_context import mark_operation_started
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
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
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
        """Report that PDF generation is unsupported by this Firefox/Camoufox server.

        Playwright's PDF API requires Chromium. This compatibility tool never
        launches another browser or writes a file. Its parameters are retained
        so existing clients receive a precise unsupported_capability response.

        Errors:
            instance_not_found     — instance does not exist
            unsupported_capability — PDF generation requires Chromium
        """
        # Retain these legacy parameters in the tool schema without pretending
        # that a Firefox renderer can honor any PDF options.
        del file_path, paper_format, landscape, print_background
        try:
            mgr.get(instance)
            return error_response(
                instance,
                "unsupported_capability",
                "PDF generation is not supported by Firefox/Camoufox. Use browser_screenshot for visual evidence.",
            )
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))


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
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
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


async def _tabs_list(ctx: BrowserContext, instance: str, mgr: InstanceManager) -> dict[str, Any]:
    tabs = [{"index": i, "url": p.url, "page_id": mgr.page_id(instance, p)} for i, p in enumerate(ctx.pages)]
    return success_response(instance, data={"tabs": tabs})


async def _tabs_new(
    ctx: BrowserContext,
    instance: str,
    mgr: InstanceManager,
    url: str | None,
) -> dict[str, Any]:
    page = await ctx.new_page()
    try:
        mark_operation_started(mgr.get(instance).instance_id, page_id=mgr.page_id(instance, page))
        if url:
            await page.goto(canonicalize_browser_url(url))
        index = ctx.pages.index(page)
        mgr.set_active_page(instance, index)
        return success_response(
            instance, data={"index": index, "url": page.url, "page_id": mgr.page_id(instance, page)}
        )
    except BaseException:
        # The tab belongs to this call until navigation and selection succeed.
        with anyio.CancelScope(shield=True), contextlib.suppress(Exception):
            with anyio.fail_after(2):
                await page.close()
        raise


def _tab_index(
    ctx: BrowserContext, instance: str, mgr: InstanceManager, index: int | None, page_id: str | None
) -> int | None:
    if page_id is not None:
        return next((i for i, page in enumerate(ctx.pages) if mgr.page_id(instance, page) == page_id), None)
    return index


async def _tabs_close(
    ctx: BrowserContext,
    instance: str,
    mgr: InstanceManager,
    index: int | None,
) -> dict[str, Any]:
    if index is None or index < 0 or index >= len(ctx.pages):
        return error_response(instance, "invalid_params", f"invalid tab index: {index}")
    page = ctx.pages[index]
    page_id = mgr.page_id(instance, page)
    active = await mgr.active_page(instance)
    mark_operation_started(mgr.get(instance).instance_id, page_id=page_id)
    await page.close()
    remaining = ctx.pages
    if remaining:
        selected = remaining.index(active) if active in remaining else min(index, len(remaining) - 1)
        mgr.set_active_page(instance, selected)
    return success_response(instance, data={"closed_index": index, "page_id": page_id})


async def _tabs_select(
    ctx: BrowserContext,
    instance: str,
    mgr: InstanceManager,
    index: int | None,
) -> dict[str, Any]:
    if index is None or index < 0 or index >= len(ctx.pages):
        return error_response(instance, "invalid_params", f"invalid tab index: {index}")
    selected = ctx.pages[index]
    mark_operation_started(mgr.get(instance).instance_id, page_id=mgr.page_id(instance, selected))
    await selected.bring_to_front()
    current_index = ctx.pages.index(selected)
    mgr.set_active_page(instance, current_index)
    return success_response(
        instance, data={"selected_index": current_index, "page_id": mgr.page_id(instance, selected)}
    )


def _register_browser_tabs(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_tabs(
        instance: str,
        action: str,
        index: int | None = None,
        url: str | None = None,
        page_id: str | None = None,
    ) -> dict[str, Any]:
        """Manage tabs (pages) within a browser instance.

        Select or close by stable page_id, or by the current index. These inputs
        are mutually exclusive. Page IDs remain stable when other tabs close.
        Every returned tab includes page_id.

        action must be one of:
          "list"   — list all open tabs with their index and URL.
                     Returns: data: {"tabs": [{"index": int, "url": str, "page_id": str}, ...]}
          "new"    — open a new tab, optionally navigating to url.
                     Returns: data: {"index": int, "url": str, "page_id": str}
          "close"  — close the tab identified by index or page_id.
                     Returns: data: {"closed_index": int, "page_id": str}
          "select" — bring the identified tab to the front, making it active
                     for subsequent tool calls. index or page_id is required.
                     Returns: data: {"selected_index": int, "page_id": str}

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
        if page_id is not None and (index is not None or action not in ("select", "close")):
            return error_response(
                instance, "invalid_params", "page_id is only valid for select/close and cannot be combined with index"
            )
        try:
            rec = mgr.get(instance)
            async with mgr.lock_for(instance):
                ctx = rec.context
                if action == "list":
                    return await _tabs_list(ctx, instance, mgr)
                if action == "new":
                    assert_no_modal(mgr, instance)
                    return await _tabs_new(ctx, instance, mgr, url)
                resolved_index = _tab_index(ctx, instance, mgr, index, page_id)
                if action == "close":
                    return await _tabs_close(ctx, instance, mgr, resolved_index)
                return await _tabs_select(ctx, instance, mgr, resolved_index)
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
