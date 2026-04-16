"""Verification tools — 4 tools."""

import logging

from fastmcp import FastMCP
from playwright.async_api import Locator, Page

from ..coercion import coerce_bool
from ..context_manager import ContextManager, assert_no_modal
from ..errors import (
    BrowserMcpError,
    InvalidParamsError,
    StaleRefError,
    VerificationFailedError,
)
from ..ref_resolver import resolve_ref
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)


async def _resolve_ref_in_any_frame(page: Page, ref: str) -> Locator:
    """Resolve a ref against the main frame first, then any child frame.

    Microsoft Playwright MCP's refs are page-scoped but elements can live in
    iframes. `resolve_ref` uses `page.locator(...)` which only searches the
    main frame selector engine path. When that fails with StaleRefError, try
    each child frame via `frame.locator("aria-ref=...")` as a fallback.

    Raises StaleRefError if the ref is not found in any frame.
    """
    try:
        return await resolve_ref(page, ref)
    except StaleRefError:
        pass
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            locator = frame.locator(f"aria-ref={ref}")
            await locator.wait_for(state="attached", timeout=500)
            return locator
        except Exception:
            continue
    raise StaleRefError(
        f"Ref '{ref}' not found in any frame of the current page snapshot. "
        f"Capture a new snapshot with browser_snapshot."
    )


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_verify_element_visible(context: str, ref: str) -> dict:
        """Verify that the element identified by ref is currently visible on the page.

        ref is a [ref=eN] value from browser_snapshot. The check is synchronous
        (no waiting) — the element must be visible at the moment of the call.
        Refs in iframes are resolved by falling back through child frames.

        Returns on success:
            data: {"visible": True, "ref": str}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a pending dialog blocks the page
            stale_ref            — ref is no longer in the accessibility tree
            verification_failed  — element exists but is not currently visible

        Use browser_wait_for(text=...) first if the element may not have appeared yet.
        """
        try:
            await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                assert_no_modal(ctx_mgr, context)
                page = await ctx_mgr.active_page(context)
                locator = await _resolve_ref_in_any_frame(page, ref)
                visible = await locator.is_visible()
                if not visible:
                    raise VerificationFailedError(f"Element {ref} is not visible")
            return success_response(context, data={"visible": True, "ref": ref})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_verify_element_visible failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_verify_list_visible(
        context: str,
        refs: list[str] | None = None,
        container_ref: str | None = None,
        items: list[str] | None = None,
    ) -> dict:
        """Verify visibility of multiple elements in either refs or container mode.

        Two mutually exclusive modes:

        1. refs mode: Pass refs=[...] — each ref must be visible.
        2. container mode: Pass container_ref + items=[...] — each item is a
           text pattern that must be visible as a descendant of container_ref
           (via ``container.get_by_text(item).first.is_visible()``).

        Returns on success:
            refs mode:      data: {"visible_refs": list[str]}
            container mode: data: {"container_ref": str, "verified_items": list[str]}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a pending dialog blocks the page
            invalid_params       — neither/both modes supplied, or container_ref
                                   without items
            stale_ref            — a ref is no longer in the accessibility tree
            verification_failed  — one or more elements/items are not visible

        Useful for post-action assertions (e.g. verify all rows of a list).
        """
        try:
            # Mode validation — before any IO.
            has_refs = refs is not None
            has_container = container_ref is not None or items is not None
            if has_refs and has_container:
                raise InvalidParamsError("refs and container_ref/items are mutually exclusive")
            if not has_refs and not has_container:
                raise InvalidParamsError("must supply either refs or container_ref+items")
            if has_container and (container_ref is None or not items):
                raise InvalidParamsError("container_ref mode requires both container_ref and items")
            if has_refs and len(refs) == 0:
                raise InvalidParamsError("refs must not be empty")

            await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                assert_no_modal(ctx_mgr, context)
                page = await ctx_mgr.active_page(context)

                if has_refs:
                    missing = []
                    for ref in refs:
                        locator = await _resolve_ref_in_any_frame(page, ref)
                        if not await locator.is_visible():
                            missing.append(ref)
                    if missing:
                        raise VerificationFailedError(f"These refs are not visible: {missing}")
                    return success_response(context, data={"visible_refs": refs})

                # container mode
                container_locator = await _resolve_ref_in_any_frame(page, container_ref)
                missing_items = []
                for item_text in items:
                    inner = container_locator.get_by_text(item_text)
                    if not await inner.first.is_visible():
                        missing_items.append(item_text)
                if missing_items:
                    raise VerificationFailedError(f"These items are not visible in container: {missing_items}")
                return success_response(
                    context,
                    data={
                        "container_ref": container_ref,
                        "verified_items": items,
                    },
                )
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_verify_list_visible failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_verify_text_visible(context: str, text: str) -> dict:
        """Verify that the given text is currently visible somewhere on the active page.

        The check is synchronous — the text must be visible at the moment of the call.
        Matching is non-exact substring; text is case-insensitive. Child frames are
        searched as well as the main frame. Uses ``.first`` to avoid strict-mode
        violations when the text matches multiple elements.

        Returns on success:
            data: {"text": str, "visible": True}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a pending dialog blocks the page
            verification_failed  — the text is not visible on any frame of the page

        Use browser_wait_for(text=...) if the text may not have appeared yet.
        """
        try:
            await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                assert_no_modal(ctx_mgr, context)
                page = await ctx_mgr.active_page(context)
                frames = [
                    page.main_frame,
                    *(f for f in page.frames if f != page.main_frame),
                ]
                found = False
                for frame in frames:
                    locator = frame.get_by_text(text).first
                    try:
                        if await locator.is_visible():
                            found = True
                            break
                    except Exception:
                        continue
                if not found:
                    raise VerificationFailedError(f"Text {text!r} is not visible on the page")
            return success_response(context, data={"text": text, "visible": True})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_verify_text_visible failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_verify_value(
        context: str,
        ref: str,
        expected_value: str,
        element_type: str = "text",
    ) -> dict:
        """Verify the value (or checked state) of an input element.

        element_type selects the comparison mode:
          - "text"     (default): read via ``locator.input_value()`` and compare
                       as a string. Use for <input>, <textarea>, <select>.
          - "checkbox" or "radio": read via ``locator.is_checked()`` and compare
                       to the boolean coercion of expected_value. Accepts bool
                       or strings like "true"/"false"/"1"/"0"/"checked"/"unchecked".

        Returns on success:
            data: {"ref": str, "value": str|bool, "element_type": str}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a pending dialog blocks the page
            invalid_params       — element_type not in {text, checkbox, radio}
            stale_ref            — ref is no longer in the accessibility tree
            verification_failed  — actual value does not match expected_value

        Use this to confirm that browser_type, browser_fill_form, or a click on
        a checkbox/radio applied correctly.
        """
        try:
            if element_type not in ("text", "checkbox", "radio"):
                raise InvalidParamsError(
                    f"element_type must be one of 'text', 'checkbox', 'radio'; got {element_type!r}"
                )
            await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                assert_no_modal(ctx_mgr, context)
                page = await ctx_mgr.active_page(context)
                locator = await _resolve_ref_in_any_frame(page, ref)
                if element_type == "text":
                    actual = await locator.input_value()
                    if actual != expected_value:
                        raise VerificationFailedError(f"Element {ref} value is {actual!r}, expected {expected_value!r}")
                else:
                    expected_bool = coerce_bool(expected_value)
                    actual = await locator.is_checked()
                    if bool(actual) != expected_bool:
                        raise VerificationFailedError(
                            f"Element {ref} checked state is {actual!r}, expected {expected_bool!r}"
                        )
            return success_response(
                context,
                data={"ref": ref, "value": actual, "element_type": element_type},
            )
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_verify_value failed")
            return error_response(context, "internal_error", str(e))
