"""Cookie and localStorage tools — 6 tools."""

import logging
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse

from fastmcp import FastMCP
from playwright.async_api import Error as PlaywrightError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from playwright._impl._api_structures import SetCookieParam

from ..context_manager import ContextManager
from ..errors import BrowserMcpError, InvalidParamsError
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)


def _extract_origin(url: str) -> str:
    """Extract scheme://host[:port] origin from a URL."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port and parsed.port not in (80, 443):
        origin += f":{parsed.port}"
    return origin


def _verify_origin(page_url: str, requested_origin: str) -> None:
    """Raise InvalidParamsError if page redirected to a different origin."""
    actual = _extract_origin(page_url)
    expected = _extract_origin(requested_origin)
    if actual != expected:
        raise InvalidParamsError(
            f"Origin mismatch: requested {requested_origin!r} but page landed on {actual!r} (likely redirect)"
        )


def _register_browser_get_cookies(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_get_cookies(
        context: str,
        urls: list[str] | None = None,
        name: str | None = None,
    ) -> dict:
        """Return cookies stored in the context, optionally filtered by URL and name.

        urls is a list of full URLs (e.g. ["https://example.com"]). When provided,
        only cookies applicable to those URLs are returned (matching domain/path rules).
        When omitted, all cookies in the context are returned. When ``name`` is
        given, the result is further filtered to cookies whose ``name`` matches
        exactly — an empty list is returned if none match (this is not an error).

        Returns on success:
            data: {"cookies": [{"name": str, "value": str, "domain": str,
                                 "path": str, "expires": float, "httpOnly": bool,
                                 "secure": bool, "sameSite": str}, ...]}

        Errors:
            context_not_found — context does not exist
        """
        try:
            ctx = await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                if urls is not None:
                    cookies = await ctx.cookies(urls)
                else:
                    cookies = await ctx.cookies()
            if name is not None:
                cookies = [c for c in cookies if c.get("name") == name]
            return success_response(context, data={"cookies": cookies})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except (PlaywrightError, OSError, RuntimeError, ValueError, TypeError) as e:
            return error_response(context, "internal_error", str(e))


def _register_browser_set_cookies(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_set_cookies(context: str, cookies: list[dict]) -> dict:
        """Add or update cookies on the context using Playwright cookie format.

        Each cookie dict must have at minimum: name, value. Playwright also
        requires either ``domain`` (with ``path``) OR ``url`` to identify
        which site the cookie belongs to — supplying either is fine. When
        both are omitted, the context's active page hostname is used as a
        default ``domain`` (if a page exists).
        Optional fields: path (default "/"), expires (Unix timestamp), httpOnly,
        secure, sameSite ("Strict"|"Lax"|"None").

        Returns on success:
            data: {"set_count": int}  — number of cookies applied

        Errors:
            context_not_found — context does not exist
            invalid_params    — cookie has neither domain nor url and no
                                active page exists to default from

        Cookies set here affect all pages in the context immediately. To persist
        them across sessions, call browser_export_context_state afterward.
        """
        try:
            ctx = await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                default_domain: str | None = None
                if ctx.pages:
                    active_page = await ctx_mgr.active_page(context)
                    parsed = urlparse(active_page.url)
                    default_domain = parsed.hostname
                processed: list[dict] = []
                for cookie in cookies:
                    normalized = cookie
                    has_domain = bool(normalized.get("domain"))
                    has_url = bool(normalized.get("url"))
                    if not has_domain and not has_url:
                        if default_domain is None:
                            return error_response(
                                context,
                                "invalid_params",
                                f"cookie {normalized.get('name')!r} has neither "
                                "domain nor url, and no active page to default from",
                            )
                        normalized = {**normalized, "domain": default_domain}
                    if "path" not in normalized and not normalized.get("url"):
                        normalized = {**normalized, "path": "/"}
                    processed.append(normalized)
                await ctx.add_cookies(cast("Sequence[SetCookieParam]", processed))
            return success_response(context, data={"set_count": len(processed)})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except (PlaywrightError, OSError, RuntimeError, ValueError, TypeError) as e:
            return error_response(context, "internal_error", str(e))


def _register_browser_clear_cookies(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_clear_cookies(context: str) -> dict:
        """Remove all cookies from the context.

        All cookies across all domains are deleted. Pages currently loaded
        in the context are not reloaded — the deletion takes effect on the
        next request that would send cookies.

        Returns on success:
            data: {"cleared": True}

        Errors:
            context_not_found — context does not exist
        """
        try:
            ctx = await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                await ctx.clear_cookies()
            return success_response(context, data={"cleared": True})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except (PlaywrightError, OSError, RuntimeError, ValueError, TypeError) as e:
            return error_response(context, "internal_error", str(e))


def _register_browser_get_local_storage(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_get_local_storage(
        context: str,
        origin: str,
        key: str | None = None,
    ) -> dict:
        """Read localStorage for the given origin.

        Opens a temporary page that navigates to origin, reads localStorage,
        then closes — the context's active page is not disturbed.
        origin must be a fully-qualified URL including scheme (e.g. "https://example.com").
        When ``key`` is provided, only the value for that key is returned
        (``None`` if the key does not exist).

        Returns on success:
            When key is None:
                data: {"items": {"key": "value", ...}, "origin": str}
            When key is given:
                data: {"key": str, "value": str | None, "origin": str}

        Errors:
            context_not_found — context does not exist
            internal_error    — navigation to origin failed (e.g. network error)
        """
        try:
            ctx = await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                page = await ctx.new_page()
                try:
                    await page.goto(origin)
                    _verify_origin(page.url, origin)
                    if key is not None:
                        value = await page.evaluate("(k) => localStorage.getItem(k)", key)
                        return success_response(
                            context,
                            data={"key": key, "value": value, "origin": origin},
                        )
                    items = await page.evaluate(
                        "() => { const out = {}; "
                        "for (let i = 0; i < localStorage.length; i++) { "
                        "  const k = localStorage.key(i); out[k] = localStorage.getItem(k); "
                        "} return out; }"
                    )
                finally:
                    await page.close()
            return success_response(context, data={"items": items, "origin": origin})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_get_local_storage failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_set_local_storage(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_set_local_storage(context: str, origin: str, items: dict[str, str]) -> dict:
        """Set localStorage key-value pairs for the given origin.

        Opens a temporary page that navigates to origin, sets each item via
        localStorage.setItem, then closes — the context's active page is not disturbed.
        All values must be strings (localStorage only stores strings).

        Returns on success:
            data: {"set_count": int, "origin": str}

        Errors:
            context_not_found — context does not exist
            internal_error    — navigation to origin failed
        """
        try:
            ctx = await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                page = await ctx.new_page()
                try:
                    await page.goto(origin)
                    _verify_origin(page.url, origin)
                    await page.evaluate(
                        "(items) => { Object.entries(items).forEach(([k, v]) => localStorage.setItem(k, v)); }",
                        items,
                    )
                finally:
                    await page.close()
            return success_response(
                context,
                data={"set_count": len(items), "origin": origin},
            )
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_set_local_storage failed")
            return error_response(context, "internal_error", str(e))


def _register_browser_clear_local_storage(mcp: FastMCP, ctx_mgr: ContextManager) -> None:

    @mcp.tool
    async def browser_clear_local_storage(
        context: str,
        origin: str | None = None,
    ) -> dict:
        """Clear localStorage entries.

        When ``origin`` is provided, opens a temporary page that navigates
        to origin, calls localStorage.clear(), then closes — the context's
        active page is not disturbed. ``origin`` must be a fully-qualified
        URL including scheme.

        When ``origin`` is omitted, localStorage is cleared on the active
        page directly (no temp page, no navigation). Use this shortcut when
        you are already on the origin whose storage you want to clear.

        Returns on success:
            data: {"cleared": True, "origin": str}  — the origin URL that was cleared

        Errors:
            context_not_found — context does not exist
            internal_error    — navigation to origin failed
        """
        try:
            ctx = await ctx_mgr.get(context)
            async with ctx_mgr.lock_for(context):
                if origin is None:
                    page = await ctx_mgr.active_page(context)
                    await page.evaluate("() => localStorage.clear()")
                    return success_response(context, data={"cleared": True, "origin": page.url})
                page = await ctx.new_page()
                try:
                    await page.goto(origin)
                    _verify_origin(page.url, origin)
                    await page.evaluate("() => localStorage.clear()")
                finally:
                    await page.close()
            return success_response(context, data={"cleared": True, "origin": origin})
        except BrowserMcpError as e:
            return error_response(context, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_clear_local_storage failed")
            return error_response(context, "internal_error", str(e))


def register(mcp: FastMCP, ctx_mgr: ContextManager) -> None:
    _register_browser_get_cookies(mcp, ctx_mgr)
    _register_browser_set_cookies(mcp, ctx_mgr)
    _register_browser_clear_cookies(mcp, ctx_mgr)
    _register_browser_get_local_storage(mcp, ctx_mgr)
    _register_browser_set_local_storage(mcp, ctx_mgr)
    _register_browser_clear_local_storage(mcp, ctx_mgr)
