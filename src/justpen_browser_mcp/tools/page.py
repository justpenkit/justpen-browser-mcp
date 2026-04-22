"""Page lifecycle tools — 1 tool.

browser_close closes the active page in an instance. The instance itself
is not destroyed; use browser_destroy_instance to drop the whole instance.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from ..errors import BrowserMcpError
from ..instance_manager import InstanceManager
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register page (tab) management tools on the MCP server."""

    @mcp.tool
    async def browser_close(instance: str) -> dict[str, Any]:
        """Close the active page (tab) in the instance, keeping the instance alive.

        Only the currently active page is closed. If the instance has other tabs,
        they remain open. The instance itself is NOT destroyed — use
        browser_destroy_instance to tear down the entire browser session.

        After closing the active page, subsequent tool calls that need a page
        (e.g. browser_navigate) will target whichever page the instance considers
        active next. Use browser_tabs to inspect and select tabs explicitly.

        Returns on success:
            data: {"closed": True}
            data: {"closed": False, "reason": "no open pages"}  — if there are no tabs to close

        Errors:
            instance_not_found — instance does not exist
        """
        try:
            rec = await mgr.get(instance)
            async with mgr.lock_for(instance):
                ctx = rec.context
                if not ctx.pages:
                    return success_response(instance, data={"closed": False, "reason": "no open pages"})
                istate = mgr.state(instance)
                closed_index = istate.active_page_index
                page = await mgr.active_page(instance)
                await page.close()
                # Update active index so the prior tab becomes active,
                # matching browser_tabs(action="close") behavior.
                remaining = len(ctx.pages)
                if remaining == 0:
                    istate.active_page_index = 0
                else:
                    istate.active_page_index = max(0, min(closed_index, remaining - 1))
            return success_response(instance, data={"closed": True})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_close failed")
            return error_response(instance, "internal_error", str(e))
