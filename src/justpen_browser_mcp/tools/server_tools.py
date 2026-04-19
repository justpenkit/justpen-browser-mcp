"""Server tools — 1 tool.

browser_status reports server health WITHOUT triggering Camoufox launch.
This is the only tool that may be called when the browser is down.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from ..camoufox import CamoufoxLauncher
from ..context_manager import ContextManager
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, ctx_mgr: ContextManager, launcher: CamoufoxLauncher) -> None:

    @mcp.tool
    async def browser_status() -> dict[str, Any]:
        """Report server health without triggering a browser launch.

        Checks whether Camoufox is currently running and how many contexts are
        active. This is the ONLY tool that can be called safely when the browser
        is not yet running — all other tools require an active context.

        Returns on success:
            data: {"browser_running": bool, "active_context_count": int,
                   "active_contexts": [{"context": str}, ...]}
            — browser_running is True if the Camoufox process is alive
            — active_contexts lists the names of all current contexts

        Never raises an error type — internal exceptions are returned as
        internal_error. No context argument is required.

        Use this to check server state before deciding whether to call
        browser_create_context or to reuse an existing session.
        """
        try:
            running = launcher.is_running()
            names = ctx_mgr.list_names()
            return success_response(
                context=None,
                data={
                    "browser_running": running,
                    "active_context_count": len(names),
                    "active_contexts": [{"context": name} for name in names],
                },
            )
        except Exception as e:
            logger.exception("browser_status failed")
            return error_response(None, "internal_error", str(e))
