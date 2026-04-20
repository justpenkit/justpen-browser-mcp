"""Page lifecycle tools — 1 tool.

browser_close closes the active page in a context. The context itself
is not destroyed; use browser_destroy_context to drop the whole context.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from ..context_manager import ContextManager
from ..errors import BrowserMcpError
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:
    """Register page (tab) management tools on the MCP server."""

    @mcp.tool
    async def browser_close(context: str) -> dict[str, Any]:
        """Close the active page (tab) in the context, keeping the context alive.

        Only the currently active page is closed. If the context has other tabs,
        they remain open. The context itself is NOT destroyed — use
        browser_destroy_context to tear down the entire browser session.

        After closing the active page, subsequent tool calls that need a page
        (e.g. browser_navigate) will target whichever page the context considers
        active next. Use browser_tabs to inspect and select tabs explicitly.

        Returns on success:
            data: {"closed": True}
            data: {"closed": False, "reason": "no open pages"}  — if there are no tabs to close

        Errors:
            context_not_found — context does not exist
        """
        try:
            await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                ctx = await ctx_mgr.get(context)
                if not ctx.pages:
                    return success_response(context, data={"closed": False, "reason": "no open pages"})
                cstate = ctx_mgr.state(context)
                closed_index = cstate.active_page_index
                page = await ctx_mgr.active_page(context)
                await page.close()
                # Update active index so the prior tab becomes active,
                # matching browser_tabs(action="close") behavior.
                remaining = len(ctx.pages)
                if remaining == 0:
                    cstate.active_page_index = 0
                else:
                    cstate.active_page_index = max(0, min(closed_index, remaining - 1))
            return success_response(context, data={"closed": True})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_close failed")
            return error_response(context, "internal_error", str(e))
