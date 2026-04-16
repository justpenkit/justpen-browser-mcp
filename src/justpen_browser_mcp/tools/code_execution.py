"""Code execution tools — 2 tools.

browser_evaluate: run a JavaScript expression on the active page.
browser_run_code: execute a Python snippet against the page object.
"""

import logging
import traceback

from fastmcp import FastMCP

from ..context_manager import ContextManager, assert_no_modal
from ..errors import BrowserMcpError, EvaluationFailedError
from ..ref_resolver import resolve_ref
from ..responses import success_response, error_response

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_evaluate(
        context: str,
        expression: str,
        ref: str | None = None,
        selector: str | None = None,
    ) -> dict:
        """Evaluate a JavaScript expression on the active page and return its result.

        expression should be a JS expression (not a statement) that can be awaited,
        e.g. "document.title" or "fetch('/api').then(r => r.json())". Arrow functions
        are supported: "() => document.body.innerText". The return value is
        serialized as JSON; non-serializable values (DOM nodes, functions) return null.

        Optional element scoping (mutually exclusive):
            ref       — accessibility ref from browser_snapshot. The expression
                        runs as locator.evaluate(expression), receiving the
                        element as its first argument.
            selector  — CSS/aria selector. Same semantics as ref but resolved
                        directly via page.locator(selector).

        When neither is provided, the expression runs at page scope.

        Returns on success:
            data: {"result": any}  — the JSON-serialized return value

        Errors:
            context_not_found    — context does not exist
            invalid_params       — both ref and selector were provided
            stale_ref            — ref no longer valid; take a fresh snapshot
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            evaluation_failed    — JS syntax error, runtime exception, or timeout

        Use browser_run_code for multi-step Python logic that needs Playwright's
        full async API (waiting for selectors, network conditions, etc.).
        """
        if ref is not None and selector is not None:
            return error_response(context, "invalid_params", "provide ref or selector, not both")
        try:
            await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                assert_no_modal(ctx_mgr, context)
                page = await ctx_mgr.active_page(context)
                try:
                    if ref is not None:
                        locator = await resolve_ref(page, ref)
                        result = await locator.evaluate(expression)
                    elif selector is not None:
                        locator = page.locator(selector)
                        result = await locator.evaluate(expression)
                    else:
                        result = await page.evaluate(expression)
                except BrowserMcpError:
                    raise
                except Exception as e:
                    raise EvaluationFailedError(str(e)) from e
            return success_response(context, data={"result": result})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_evaluate failed")
            return error_response(context, "internal_error", str(e))

    @mcp.tool
    async def browser_run_code(context: str, code: str) -> dict:
        """Execute a Python async code snippet with full Playwright access.

        The snippet runs as the body of an async function. These locals are
        in scope:
            page    — the active Playwright Page object
            context — the Playwright BrowserContext object
            ctx_mgr — the ContextManager (advanced use only)

        Use a `return` statement to return a value back to the agent.
        Any exception raised in the snippet is caught and returned as
        evaluation_failed.

        Returns on success:
            data: {"result": any}  — the return value of the snippet, or None

        Errors:
            context_not_found    — context does not exist
            modal_state_blocked  — a dialog or file chooser is pending
            evaluation_failed    — Python exception raised inside the snippet;
                                   error message includes the original traceback

        Example code: `await page.wait_for_selector('#done'); return await page.title()`
        """
        try:
            ctx = await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                assert_no_modal(ctx_mgr, context)
                page = await ctx_mgr.active_page(context)
                wrapper = "async def _user_code(page, context, ctx_mgr):\n" + "\n".join(
                    "    " + line for line in code.split("\n")
                )
                try:
                    namespace: dict = {}
                    exec(wrapper, namespace)
                    result = await namespace["_user_code"](page, ctx, ctx_mgr)
                except Exception as e:
                    tb = traceback.format_exc()
                    raise EvaluationFailedError(f"run_code failed:\n{tb}") from e
            return success_response(context, data={"result": result})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_run_code failed")
            return error_response(context, "internal_error", str(e))
