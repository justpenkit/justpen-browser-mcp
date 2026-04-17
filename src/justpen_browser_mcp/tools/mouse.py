"""Mouse positional tools — 6 tools."""

import contextlib
import logging
from typing import Literal, cast

from fastmcp import FastMCP
from playwright.async_api import TimeoutError as PWTimeout

from ..context_manager import ContextManager, assert_no_modal
from ..errors import BrowserMcpError, InvalidParamsError
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)

_VALID_BUTTONS: frozenset[str] = frozenset({"left", "middle", "right"})


def _validated_button(button: str) -> Literal["left", "middle", "right"]:
    if button not in _VALID_BUTTONS:
        raise InvalidParamsError(f"button must be 'left', 'middle', or 'right'; got {button!r}")
    return cast("Literal['left', 'middle', 'right']", button)


def _register_browser_mouse_click_xy(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_mouse_click_xy(
        context: str,
        x: int,
        y: int,
        button: str = "left",
        click_count: int = 1,
        delay_ms: int = 0,
    ) -> dict:
        """Click the mouse at an absolute pixel position on the active page.

        This is a low-level positional tool. Prefer browser_click(ref=...) when
        the target element is in the accessibility snapshot — it is more reliable
        and does not depend on exact layout coordinates.

        x, y are page-relative pixels (top-left is 0,0). button is "left",
        "right", or "middle" (default "left"). click_count is the number of
        clicks to deliver (default 1; use 2 for a double-click). delay_ms is
        the delay in milliseconds between mousedown and mouseup (default 0).

        Returns on success:
            data: {"clicked_at": [x, y], "button": str}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                await page.mouse.click(x, y, button=_validated_button(button), click_count=click_count, delay=delay_ms)
                with contextlib.suppress(PWTimeout):
                    await page.wait_for_load_state("domcontentloaded", timeout=2000)
            return success_response(context, data={"clicked_at": [x, y], "button": button})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_mouse_click_xy failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_mouse_move_xy(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_mouse_move_xy(context: str, x: int, y: int) -> dict:
        """Move the mouse cursor to an absolute pixel position without clicking.

        This is a low-level positional tool useful for triggering hover effects
        at specific coordinates. Prefer browser_hover(ref=...) when the target
        is in the accessibility snapshot.

        x, y are page-relative pixels (top-left is 0,0).

        Returns on success:
            data: {"moved_to": [x, y]}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                await page.mouse.move(x, y)
            return success_response(context, data={"moved_to": [x, y]})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_mouse_move_xy failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_mouse_down(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_mouse_down(context: str, button: str = "left") -> dict:
        """Press a mouse button down (without releasing it).

        Low-level tool for building custom gesture sequences. button is "left",
        "right", or "middle" (default "left"). Pair with browser_mouse_up to
        complete a press-and-release. For drag operations, use browser_mouse_drag_xy.

        Returns on success:
            data: {"button_down": str}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                await page.mouse.down(button=_validated_button(button))
            return success_response(context, data={"button_down": button})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_mouse_down failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_mouse_up(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_mouse_up(context: str, button: str = "left") -> dict:
        """Release a previously pressed mouse button.

        Low-level tool to be used after browser_mouse_down. button must match
        the button passed to browser_mouse_down. For drag operations, use
        browser_mouse_drag_xy which handles the full sequence.

        Returns on success:
            data: {"button_up": str}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                await page.mouse.up(button=_validated_button(button))
            return success_response(context, data={"button_up": button})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_mouse_up failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_mouse_drag_xy(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_mouse_drag_xy(context: str, from_x: int, from_y: int, to_x: int, to_y: int) -> dict:
        """Drag the mouse from one absolute pixel position to another.

        Performs: move to (from_x, from_y), press left button, move to (to_x, to_y),
        release. All coordinates are page-relative pixels (top-left is 0,0).

        For element-to-element drag, prefer browser_drag(source_ref, target_ref)
        which uses accessibility refs and is more stable across layout changes.

        Returns on success:
            data: {"from": [from_x, from_y], "to": [to_x, to_y]}

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
        """
        try:
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                await page.mouse.move(from_x, from_y)
                await page.mouse.down()
                await page.mouse.move(to_x, to_y)
                await page.mouse.up()
                with contextlib.suppress(PWTimeout):
                    await page.wait_for_load_state("domcontentloaded", timeout=2000)
            return success_response(context, data={"from": [from_x, from_y], "to": [to_x, to_y]})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_mouse_drag_xy failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_mouse_wheel(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_mouse_wheel(context: str, delta_x: int = 0, delta_y: int = 0) -> dict:
        """Scroll the mouse wheel by the given pixel deltas at the current cursor position.

        delta_x is horizontal scroll (positive = right), delta_y is vertical
        scroll (positive = down). Both default to 0 but at least one must be
        non-zero. Coordinates are in CSS pixels. The scroll is delivered at
        the current mouse cursor position, so position the cursor with
        browser_mouse_move_xy first if targeting a specific scrollable container.

        Returns on success:
            data: {"scrolled": [delta_x, delta_y]}

        Errors:
            context_not_found    — context does not exist
            invalid_params       — both delta_x and delta_y are zero
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
        """
        try:
            if delta_x == 0 and delta_y == 0:
                return error_response(
                    context,
                    "invalid_params",
                    "at least one of delta_x or delta_y must be non-zero",
                )
            await ctx_mgr.get(context)
            assert_no_modal(ctx_mgr, context)
            async with ctx_mgr.lock_for(context):
                page = await ctx_mgr.active_page(context)
                await page.mouse.wheel(delta_x, delta_y)
            return success_response(context, data={"scrolled": [delta_x, delta_y]})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_mouse_wheel failed")
            return error_response(context, "internal_error", str(e))


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:
    _register_browser_mouse_click_xy(mcp, ctx_mgr)
    _register_browser_mouse_move_xy(mcp, ctx_mgr)
    _register_browser_mouse_down(mcp, ctx_mgr)
    _register_browser_mouse_up(mcp, ctx_mgr)
    _register_browser_mouse_drag_xy(mcp, ctx_mgr)
    _register_browser_mouse_wheel(mcp, ctx_mgr)
