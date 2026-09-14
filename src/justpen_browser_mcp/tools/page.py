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
    async def browser_close(instance: str, *, page_id: str | None = None) -> dict[str, Any]:
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
            rec = mgr.get(instance)
            async with mgr.lock_for(instance):
                ctx = rec.context
                if not ctx.pages and page_id is None:
                    return success_response(instance, data={"closed": False, "reason": "no open pages"})
                page = await mgr.target_page(instance, page_id)
                selected = mgr.state(instance).active_page
                closed_index = ctx.pages.index(page)
                await page.close()
                if ctx.pages:
                    mgr.set_active_page(
                        instance,
                        ctx.pages.index(selected) if selected in ctx.pages else min(closed_index, len(ctx.pages) - 1),
                    )
            return success_response(instance, data={"closed": True})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_close failed")
            return error_response(instance, "internal_error", str(e))
