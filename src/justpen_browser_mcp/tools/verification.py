"""Verification tools — 4 tools."""

import logging
from typing import Any

from fastmcp import FastMCP
from playwright.async_api import Error as PlaywrightError, Locator, Page

from ..coercion import coerce_bool
from ..errors import (
    BrowserMcpError,
    StaleRefError,
)
from ..instance_manager import InstanceManager, assert_no_modal
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
        except PlaywrightError:
            continue
        else:
            return locator
    raise StaleRefError(
        f"Ref '{ref}' not found in any frame of the current page snapshot. "
        f"Capture a new snapshot with browser_snapshot."
    )


def _validate_list_visible_params(
    refs: list[str] | None,
    container_ref: str | None,
    items: list[str] | None,
) -> str | None:
    """Return an error message string if mode params are invalid, else None."""
    has_refs = refs is not None
    has_container = container_ref is not None or items is not None
    if has_refs and has_container:
        return "refs and container_ref/items are mutually exclusive"
    if not has_refs and not has_container:
        return "must supply either refs or container_ref+items"
    if has_container and (container_ref is None or not items):
        return "container_ref mode requires both container_ref and items"
    if has_refs and len(refs) == 0:
        return "refs must not be empty"
    return None


async def _verify_refs_visible(page: Page, refs: list[str]) -> list[str]:
    """Return list of refs that are not visible (empty on full success)."""
    missing: list[str] = []
    for ref in refs:
        locator = await _resolve_ref_in_any_frame(page, ref)
        if not await locator.is_visible():
            missing.append(ref)
    return missing


async def _verify_items_in_container(
    page: Page,
    container_ref: str,
    items: list[str],
) -> list[str]:
    """Return list of item texts that are not visible in the container (empty on full success)."""
    container_locator = await _resolve_ref_in_any_frame(page, container_ref)
    missing: list[str] = []
    for item_text in items:
        inner = container_locator.get_by_text(item_text)
        if not await inner.first.is_visible():
            missing.append(item_text)
    return missing


def _register_browser_verify_element_visible(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_verify_element_visible(instance: str, ref: str) -> dict[str, Any]:
        """Verify that the element identified by ref is currently visible on the page.

        ref is a [ref=eN] value from browser_snapshot. The check is synchronous
        (no waiting) — the element must be visible at the moment of the call.
        Refs in iframes are resolved by falling back through child frames.

        Returns on success:
            data: {"visible": True, "ref": str}

        Errors:
            instance_not_found   — instance does not exist
            modal_state_blocked  — a pending dialog blocks the page
            stale_ref            — ref is no longer in the accessibility tree
            verification_failed  — element exists but is not currently visible

        Use browser_wait_for(text=...) first if the element may not have appeared yet.
        """
        try:
            mgr.get(instance)
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                page = await mgr.active_page(instance)
                locator = await _resolve_ref_in_any_frame(page, ref)
                visible = await locator.is_visible()
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_verify_element_visible failed")
            return error_response(instance, "internal_error", str(e))
        if not visible:
            return error_response(instance, "verification_failed", f"Element {ref} is not visible")
        return success_response(instance, data={"visible": True, "ref": ref})


def _register_browser_verify_list_visible(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_verify_list_visible(
        instance: str,
        refs: list[str] | None = None,
        container_ref: str | None = None,
        items: list[str] | None = None,
    ) -> dict[str, Any]:
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
            instance_not_found   — instance does not exist
            modal_state_blocked  — a pending dialog blocks the page
            invalid_params       — neither/both modes supplied, or container_ref
                                   without items
            stale_ref            — a ref is no longer in the accessibility tree
            verification_failed  — one or more elements/items are not visible

        Useful for post-action assertions (e.g. verify all rows of a list).
        """
        validation_error = _validate_list_visible_params(refs, container_ref, items)
        if validation_error is not None:
            return error_response(instance, "invalid_params", validation_error)

        try:
            mgr.get(instance)
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                page = await mgr.active_page(instance)

                if refs is not None:
                    missing = await _verify_refs_visible(page, refs)
                    if missing:
                        return error_response(
                            instance,
                            "verification_failed",
                            f"These refs are not visible: {missing}",
                        )
                    return success_response(instance, data={"visible_refs": refs})

                if container_ref is None or items is None:
                    return error_response(instance, "invalid_params", "container_ref and items are required")
                missing_items = await _verify_items_in_container(page, container_ref, items)
                if missing_items:
                    return error_response(
                        instance,
                        "verification_failed",
                        f"These items are not visible in container: {missing_items}",
                    )
                return success_response(
                    instance,
                    data={
                        "container_ref": container_ref,
                        "verified_items": items,
                    },
                )
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_verify_list_visible failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_verify_text_visible(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_verify_text_visible(instance: str, text: str) -> dict[str, Any]:
        """Verify that the given text is currently visible somewhere on the active page.

        The check is synchronous — the text must be visible at the moment of the call.
        Matching is non-exact substring; text is case-insensitive. Child frames are
        searched as well as the main frame. Uses ``.first`` to avoid strict-mode
        violations when the text matches multiple elements.

        Returns on success:
            data: {"text": str, "visible": True}

        Errors:
            instance_not_found   — instance does not exist
            modal_state_blocked  — a pending dialog blocks the page
            verification_failed  — the text is not visible on any frame of the page

        Use browser_wait_for(text=...) if the text may not have appeared yet.
        """
        try:
            mgr.get(instance)
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                page = await mgr.active_page(instance)
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
                    except PlaywrightError:
                        continue
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_verify_text_visible failed")
            return error_response(instance, "internal_error", str(e))
        if not found:
            return error_response(instance, "verification_failed", f"Text {text!r} is not visible on the page")
        return success_response(instance, data={"text": text, "visible": True})


def _register_browser_verify_value(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_verify_value(
        instance: str,
        ref: str,
        expected_value: str,
        element_type: str = "text",
    ) -> dict[str, Any]:
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
            instance_not_found   — instance does not exist
            modal_state_blocked  — a pending dialog blocks the page
            invalid_params       — element_type not in {text, checkbox, radio}
            stale_ref            — ref is no longer in the accessibility tree
            verification_failed  — actual value does not match expected_value

        Use this to confirm that browser_type, browser_fill_form, or a click on
        a checkbox/radio applied correctly.
        """
        if element_type not in ("text", "checkbox", "radio"):
            return error_response(
                instance,
                "invalid_params",
                f"element_type must be one of 'text', 'checkbox', 'radio'; got {element_type!r}",
            )
        try:
            mgr.get(instance)
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                page = await mgr.active_page(instance)
                locator = await _resolve_ref_in_any_frame(page, ref)
                if element_type == "text":
                    actual = await locator.input_value()
                    if actual != expected_value:
                        return error_response(
                            instance,
                            "verification_failed",
                            f"Element {ref} value is {actual!r}, expected {expected_value!r}",
                        )
                else:
                    expected_bool = coerce_bool(expected_value)
                    actual = await locator.is_checked()
                    if bool(actual) != expected_bool:
                        return error_response(
                            instance,
                            "verification_failed",
                            f"Element {ref} checked state is {actual!r}, expected {expected_bool!r}",
                        )
            return success_response(
                instance,
                data={"ref": ref, "value": actual, "element_type": element_type},
            )
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_verify_value failed")
            return error_response(instance, "internal_error", str(e))


def register(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register DOM verification tools on the MCP server."""
    _register_browser_verify_element_visible(mcp, mgr)
    _register_browser_verify_list_visible(mcp, mgr)
    _register_browser_verify_text_visible(mcp, mgr)
    _register_browser_verify_value(mcp, mgr)
