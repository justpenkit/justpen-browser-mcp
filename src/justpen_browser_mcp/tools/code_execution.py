"""Code execution tools — 2 tools.

browser_evaluate: run a JavaScript expression on the active page.
browser_run_code: execute a Python snippet against the page object.
"""

import logging
import traceback
from typing import Any

from fastmcp import FastMCP

from ..errors import BrowserMcpError, EvaluationFailedError
from ..instance_manager import InstanceManager, assert_no_modal
from ..ref_resolver import resolve_ref
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)


def _register_browser_evaluate(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_evaluate(
        instance: str,
        expression: str,
        ref: str | None = None,
        selector: str | None = None,
    ) -> dict[str, Any]:
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
            instance_not_found   — instance does not exist
            invalid_params       — both ref and selector were provided
            stale_ref            — ref no longer valid; take a fresh snapshot
            modal_state_blocked  — a dialog or file-chooser is pending; resolve it first
            evaluation_failed    — JS syntax error, runtime exception, or timeout

        Use browser_run_code for multi-step Python logic that needs Playwright's
        full async API (waiting for selectors, network conditions, etc.).
        """
        if ref is not None and selector is not None:
            return error_response(instance, "invalid_params", "provide ref or selector, not both")
        try:
            await mgr.get(instance)
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                page = await mgr.active_page(instance)
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
            return success_response(instance, data={"result": result})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_evaluate failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_run_code(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_run_code(instance: str, code: str) -> dict[str, Any]:
        """Execute a Python async code snippet with full Playwright access.

        The snippet runs as the body of an async function. These locals are
        in scope:
            page    — the active Playwright Page object
            context — the Playwright BrowserContext object
            mgr     — the InstanceManager (advanced use only)

        Use a `return` statement to return a value back to the agent.
        Any exception raised in the snippet is caught and returned as
        evaluation_failed.

        Returns on success:
            data: {"result": any}  — the return value of the snippet, or None

        Errors:
            instance_not_found   — instance does not exist
            modal_state_blocked  — a dialog or file chooser is pending
            evaluation_failed    — Python exception raised inside the snippet;
                                   error message includes the original traceback

        Example code: `await page.wait_for_selector('#done'); return await page.title()`
        """
        try:
            rec = await mgr.get(instance)
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                page = await mgr.active_page(instance)
                # Expose the Playwright BrowserContext as 'context' for backwards
                # compatibility with existing code snippets that reference it by that name.
                playwright_context = rec.context
                wrapper = "async def _user_code(page, context, mgr):\n" + "\n".join(
                    "    " + line for line in code.split("\n")
                )
                try:
                    namespace: dict[str, Any] = {}
                    exec(wrapper, namespace)  # noqa: S102 — tool purpose: run agent-supplied Python against the browser
                    result = await namespace["_user_code"](page, playwright_context, mgr)
                except Exception as e:
                    tb = traceback.format_exc()
                    raise EvaluationFailedError(f"run_code failed:\n{tb}") from e
            return success_response(instance, data={"result": result})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_run_code failed")
            return error_response(instance, "internal_error", str(e))


def register(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register in-page code execution tools on the MCP server."""
    _register_browser_evaluate(mcp, mgr)
    _register_browser_run_code(mcp, mgr)
