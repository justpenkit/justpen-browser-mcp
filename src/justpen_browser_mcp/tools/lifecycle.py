"""Context lifecycle tools — 5 tools.

browser_create_context, browser_load_context_state, browser_export_context_state,
browser_destroy_context, browser_list_contexts.
"""

import logging

from fastmcp import FastMCP

from ..context_manager import ContextManager
from ..errors import BrowserMcpError
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_create_context(context: str, state_path: str | None = None) -> dict:
        """Create a new isolated browser context (like a fresh browser profile).

        state_path is optional. When supplied, the context is pre-loaded with
        the Playwright storage_state JSON at that path (cookies + localStorage).
        The file must exist and be valid JSON produced by browser_export_context_state.

        Returns on success:
            data: {"created": True}

        Errors:
            context_already_exists — a context with this name already exists
            state_file_not_found   — state_path supplied but the file doesn't exist
            invalid_state_file     — state_path exists but cannot be parsed as storage state

        Each context maps to one Playwright BrowserContext. No pages exist
        immediately after creation. The first tool call that needs a page
        (e.g. browser_navigate) implicitly creates one, or you can create
        one explicitly with browser_tabs(action="new").
        Contexts are fully isolated: cookies, localStorage, and sessions do not
        cross context boundaries.
        """
        try:
            await ctx_mgr.create(context, state_path=state_path)
            return success_response(context=context, data={"created": True})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_create_context failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_load_context_state(context: str, state_path: str) -> dict:
        """Replace the context's cookies and localStorage in-place from a saved state file.

        Unlike browser_create_context(state_path=...), this does NOT recreate the context —
        it applies the stored state to the already-running context. The active page and
        all tabs remain open; only the cookie jar and localStorage are replaced.

        Returns on success:
            data: {"loaded_from": str}  — the path that was applied

        Errors:
            context_not_found    — context does not exist; call browser_create_context first
            state_file_not_found — the file at state_path does not exist
            invalid_state_file   — file exists but is not valid Playwright storage_state JSON
        """
        try:
            async with ctx_mgr.lock_for(context):
                failed_origins = await ctx_mgr.load_state(context, state_path)
            data: dict = {"loaded_from": state_path}
            if failed_origins:
                data["failed_origins"] = failed_origins
            return success_response(context=context, data=data)
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_load_context_state failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_export_context_state(context: str, state_path: str) -> dict:
        """Write the context's current cookies and localStorage to a JSON file.

        Produces a Playwright storage_state JSON file. Parent directories are
        created automatically if they don't exist. The file can later be passed
        to browser_create_context(state_path=...) or browser_load_context_state.

        Returns on success:
            data: {"saved_to": str}  — the absolute path the file was written to

        Errors:
            context_not_found — context does not exist

        Use this to persist login sessions across agent runs or to share
        authentication state between contexts.
        """
        try:
            async with ctx_mgr.lock_for(context):
                await ctx_mgr.export_state(context, state_path)
            return success_response(context=context, data={"saved_to": state_path})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_export_context_state failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_destroy_context(context: str) -> dict:
        """Close the context and remove it from the server's registry.

        All pages in the context are closed. If this was the last active context,
        Camoufox is automatically shut down (browser process exits). The next
        browser_create_context call will re-launch it lazily.

        Returns on success:
            data: {"destroyed": True}

        Errors:
            context_not_found — context does not exist

        This is the correct way to fully tear down a browser session. For closing
        a single tab while keeping the context alive, use browser_close instead.
        """
        try:
            await ctx_mgr.destroy(context)
            return success_response(context=context, data={"destroyed": True})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_destroy_context failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_list_contexts() -> dict:
        """List all active browser contexts with summary information.

        Returns on success:
            data: {"contexts": [{"context": str, "page_count": int,
                                  "active_url": str, "cookie_count": int}, ...]}

        Never raises an error — if no contexts exist the list is empty.
        This is a server-level tool: no context argument is needed.

        Use this to discover what sessions are alive before deciding which
        context to use for subsequent tool calls.
        """
        try:
            contexts = await ctx_mgr.list()
            return success_response(context=None, data={"contexts": contexts})
        except Exception as e:
            logger.exception("browser_list_contexts failed")
            return error_response(None, "internal_error", str(e))
