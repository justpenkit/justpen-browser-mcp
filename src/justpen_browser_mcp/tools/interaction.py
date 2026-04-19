"""Interaction tools — 9 tools.

browser_click, browser_type, browser_fill_form, browser_select_option,
browser_hover, browser_drag, browser_press_key, browser_file_upload,
browser_handle_dialog.
"""

import contextlib
import logging
from typing import Any

from fastmcp import FastMCP
from playwright.async_api import Page, TimeoutError as PWTimeout

from ..coercion import coerce_bool
from ..context_manager import ContextManager, assert_no_modal
from ..errors import BrowserMcpError
from ..ref_resolver import resolve_ref
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)

_VALID_BUTTONS = {"left", "right", "middle"}
_VALID_MODIFIERS = {"Alt", "Control", "ControlOrMeta", "Meta", "Shift"}


def _register_browser_click(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_click(
        context: str,
        ref: str,
        *,
        double_click: bool = False,
        button: str = "left",
        modifiers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Click an element by its accessibility ref from browser_snapshot.

        ref is the [ref=eN] value annotated in the browser_snapshot output,
        e.g. "e5". The element is scrolled into view and clicked at its center.

        double_click=True performs a double-click instead of a single click.
        button is one of "left" (default), "right", "middle".
        modifiers is an optional list of keyboard modifiers held during the
        click. Valid members: "Alt", "Control", "ControlOrMeta", "Meta", "Shift".

        Returns on success:
            data: {"clicked": str}  — the ref that was clicked

        Errors:
            context_not_found    — context does not exist
            stale_ref            — ref is no longer in the page's accessibility tree;
                                   take a fresh snapshot and locate the element again
            invalid_params       — unknown button or modifier value
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            internal_error       — element not clickable (obscured, disabled, etc.)
        """
        try:
            if button not in _VALID_BUTTONS:
                return error_response(context, "invalid_params", f"unknown button: {button!r}")
            if modifiers:
                bad = [m for m in modifiers if m not in _VALID_MODIFIERS]
                if bad:
                    return error_response(context, "invalid_params", f"unknown modifiers: {bad!r}")
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                locator = await resolve_ref(page, ref)
                options: dict[str, Any] = {"button": button}
                if modifiers:
                    options["modifiers"] = modifiers
                if double_click:
                    await locator.dblclick(**options)
                else:
                    await locator.click(**options)
            return success_response(context, data={"clicked": ref})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_click failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_type(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_type(
        context: str,
        ref: str,
        text: str,
        *,
        clear_first: bool = True,
        submit: bool = False,
    ) -> dict[str, Any]:
        """Type text into an editable element identified by its accessibility ref.

        ref is the [ref=eN] value from browser_snapshot.
        clear_first defaults to True: the existing value is cleared before typing
        (uses fill, which is instant). When clear_first=False, the text is appended
        to whatever is already in the field (uses type, which simulates keystrokes).

        submit=True presses Enter after typing and best-effort waits for the
        page to reach domcontentloaded (for forms that navigate on submit).

        Returns on success:
            data: {"typed_into": str}  — the ref that received the text

        Errors:
            context_not_found    — context does not exist
            stale_ref            — ref is no longer valid; take a fresh snapshot
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            internal_error       — element is not editable or is disabled
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                locator = await resolve_ref(page, ref)
                if clear_first:
                    await locator.fill(text)
                else:
                    await locator.type(text)
                if submit:
                    await locator.press("Enter")
                    with contextlib.suppress(PWTimeout):
                        await page.wait_for_load_state("domcontentloaded", timeout=2000)
            return success_response(context, data={"typed_into": ref})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_type failed")
            return error_response(context, "internal_error", str(e))


async def _fill_form_field(page: Page, field: dict[str, Any]) -> str | None:
    """Fill one form field; return None on success or an error message on validation failure."""
    if "ref" not in field:
        return "field is missing required 'ref' key"
    if "value" not in field:
        return "field is missing required 'value' key"
    type_ = field.get("type", "textbox")
    locator = await resolve_ref(page, field["ref"])
    value = field["value"]
    if type_ == "textbox":
        await locator.fill(str(value))
    elif type_ in ("checkbox", "radio"):
        await locator.set_checked(checked=coerce_bool(value))
    elif type_ == "combobox":
        await locator.select_option(str(value))
    else:
        return f"unknown field type: {type_!r}"
    return None


def _register_browser_fill_form(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_fill_form(context: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
        """Fill multiple form fields in one call, in the order provided.

        fields is a list of {"ref": str, "value": any, "type": str?} dicts.
        The optional "type" field is one of:
            "textbox"  (default) — uses locator.fill(str(value))
            "checkbox"           — uses locator.set_checked(coerce_bool(value))
            "radio"              — uses locator.set_checked(coerce_bool(value))
            "combobox"           — uses locator.select_option(str(value))

        coerce_bool accepts real booleans or the case-insensitive strings
        "true"/"false"/"1"/"0"/"checked"/"unchecked"/"yes"/"no" (and ""
        → False). Any other value for a checkbox/radio field raises
        invalid_params (the previous behavior used Python's bool(),
        which silently converted "false" and "0" to True).

        All refs must be from the current snapshot.

        Returns on success:
            data: {"filled_count": int}  — number of fields filled

        Errors:
            context_not_found    — context does not exist
            stale_ref            — one of the refs is no longer valid
            invalid_params       — unknown field "type"
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            internal_error       — a field is not editable or fill failed

        If any field fails, filling stops at that field — earlier fields
        retain their new values. Take a fresh snapshot to verify the form state.
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                for field in fields:
                    error = await _fill_form_field(page, field)
                    if error is not None:
                        return error_response(context, "invalid_params", error)
            return success_response(context, data={"filled_count": len(fields)})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_fill_form failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_select_option(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_select_option(context: str, ref: str, value: str | list[str]) -> dict[str, Any]:
        """Select an option in a <select> dropdown by its value attribute.

        ref is the [ref=eN] of the <select> element from browser_snapshot.
        value is the HTML value attribute of the option to select (not the
        display label). To find valid values, inspect the snapshot for the
        option elements nested under the select.

        For multi-select elements, value may be a list of values to select.

        Returns on success:
            data: {"selected": str | list[str]}  — the value(s) that were selected

        Errors:
            context_not_found    — context does not exist
            stale_ref            — ref is no longer valid; take a fresh snapshot
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            internal_error       — value not found in options, or element not a select
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                locator = await resolve_ref(page, ref)
                await locator.select_option(value)
            return success_response(context, data={"selected": value})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_select_option failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_hover(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_hover(context: str, ref: str) -> dict[str, Any]:
        """Hover the mouse over an element identified by its accessibility ref.

        ref is the [ref=eN] value from browser_snapshot. The element is scrolled
        into view and the mouse cursor is positioned at its center. Useful for
        triggering hover-activated menus, tooltips, or CSS :hover styles.

        Returns on success:
            data: {"hovered": str}  — the ref that was hovered

        Errors:
            context_not_found    — context does not exist
            stale_ref            — ref is no longer valid; take a fresh snapshot
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                locator = await resolve_ref(page, ref)
                await locator.hover()
            return success_response(context, data={"hovered": ref})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_hover failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_drag(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_drag(context: str, source_ref: str, target_ref: str) -> dict[str, Any]:
        """Drag an element to a target element using accessibility refs.

        Both source_ref and target_ref are [ref=eN] values from browser_snapshot.
        Performs a full drag sequence: mouse down on source, move to target center,
        mouse up. Works for most drag-and-drop implementations that use pointer events.

        Returns on success:
            data: {"dragged": str, "to": str}  — source and target refs

        Errors:
            context_not_found    — context does not exist
            stale_ref            — either ref is no longer valid; take a fresh snapshot
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            internal_error       — drag not supported by the element or framework
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                source = await resolve_ref(page, source_ref)
                target = await resolve_ref(page, target_ref)
                await source.drag_to(target)
            return success_response(context, data={"dragged": source_ref, "to": target_ref})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_drag failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_press_key(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_press_key(context: str, key: str) -> dict[str, Any]:
        """Press a keyboard key on the active page (sent to whatever has focus).

        key follows Playwright key naming: simple keys like "Enter", "Tab",
        "Escape", "ArrowDown", and combinations like "Control+A", "Shift+Tab".
        See Playwright keyboard documentation for the full list of key names.

        Returns on success:
            data: {"pressed": str}  — the key string that was sent

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            internal_error       — key name not recognized by Playwright
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                await page.keyboard.press(key)
                if key.lower() == "enter":
                    with contextlib.suppress(PWTimeout):
                        await page.wait_for_load_state("domcontentloaded", timeout=2000)
            return success_response(context, data={"pressed": key})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_press_key failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_file_upload(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_file_upload(context: str, paths: list[str] | None = None) -> dict[str, Any]:
        """Resolve a pending native file-chooser dialog.

        Consumes a pending file-chooser captured by the modal-state listener
        (i.e. one that opened in response to a prior click on a file input).
        If paths is a non-empty list, those files are attached. If paths is
        None or empty, the file chooser is cancelled (no files attached).

        Returns on success:
            data: {"uploaded_count": int}  — number of files attached
            data: {"cancelled": True}      — when called without paths

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — no file chooser is currently pending
            internal_error       — set_files failed (path not found, etc.)
        """
        try:
            await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                state = ctx_mgr.consume_modal_state(context, "filechooser")
                if state is None:
                    return error_response(
                        context,
                        "modal_state_blocked",
                        "no file chooser is currently pending",
                    )
                file_chooser = state["object"]
                if not paths:
                    # Cancel: don't call set_files. The FileChooser object
                    # will be GC'd; the dialog resolves on next interaction.
                    return success_response(context, data={"cancelled": True})
                try:
                    await file_chooser.set_files(paths)
                except Exception:
                    # Re-insert modal state only if the page is still alive,
                    # otherwise the file chooser is dead and re-queuing it
                    # would wedge the context behind modal_state_blocked.
                    page = state.get("page")
                    if page is not None and not page.is_closed():
                        ctx_mgr.state(context).modal_states.insert(0, state)
                    raise
            return success_response(context, data={"uploaded_count": len(paths)})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_file_upload failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_handle_dialog(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_handle_dialog(context: str, *, accept: bool, prompt_text: str | None = None) -> dict[str, Any]:
        """Resolve a pending JavaScript dialog (alert/confirm/prompt).

        Consumes a pending dialog captured by the modal-state listener. The
        dialog must already be open (triggered by a prior tool call); this
        tool does NOT pre-register a handler.

        accept=True calls dialog.accept(prompt_text or ""); accept=False
        calls dialog.dismiss(). prompt_text is only meaningful for prompt
        dialogs and is ignored otherwise.

        Returns on success:
            data: {
                "action": "accepted" | "dismissed",
                "dialog_type": str,  # "alert", "confirm", or "prompt"
                "message": str,      # the dialog's message text
            }

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — no dialog is currently pending
        """
        try:
            await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                state = ctx_mgr.consume_modal_state(context, "dialog")
                if state is None:
                    return error_response(
                        context,
                        "modal_state_blocked",
                        "no dialog is currently pending",
                    )
                dialog = state["object"]
                page = state["page"]
                if accept:
                    await dialog.accept(prompt_text or "")
                else:
                    await dialog.dismiss()
                # Best-effort page stabilization after dialog resolution.
                with contextlib.suppress(Exception):
                    await page.wait_for_load_state("domcontentloaded", timeout=1000)
            return success_response(
                context,
                data={
                    "action": "accepted" if accept else "dismissed",
                    "dialog_type": dialog.type,
                    "message": dialog.message,
                },
            )
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_handle_dialog failed")
            return error_response(context, "internal_error", str(e))


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:
    _register_browser_click(mcp, ctx_mgr)
    _register_browser_type(mcp, ctx_mgr)
    _register_browser_fill_form(mcp, ctx_mgr)
    _register_browser_select_option(mcp, ctx_mgr)
    _register_browser_hover(mcp, ctx_mgr)
    _register_browser_drag(mcp, ctx_mgr)
    _register_browser_press_key(mcp, ctx_mgr)
    _register_browser_file_upload(mcp, ctx_mgr)
    _register_browser_handle_dialog(mcp, ctx_mgr)
