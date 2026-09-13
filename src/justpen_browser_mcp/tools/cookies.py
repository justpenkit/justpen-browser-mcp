"""Cookie and localStorage tools — 6 tools."""

import json
import logging
from typing import TYPE_CHECKING, Any, Literal, cast
from urllib.parse import urlparse

import anyio
from fastmcp import FastMCP
from playwright.async_api import BrowserContext, Error as PlaywrightError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from playwright._impl._api_structures import SetCookieParam

from ..errors import BrowserMcpError, InvalidParamsError
from ..instance_manager import InstanceManager, assert_no_modal
from ..operation_context import mark_operation_started
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)

_STORAGE_CLOSE_TIMEOUT_SECONDS = 2


_STORAGE_OPERATION = """({origin, operation, key, items}) => {
    const expected = new URL(origin).origin;
    const actual = location.origin;
    if (expected === 'null' || actual !== expected) {
        return JSON.stringify({mismatch: true, origin: actual});
    }
    if (operation === 'set') {
        Object.entries(JSON.parse(items)).forEach(([k, v]) => localStorage.setItem(k, v));
        return JSON.stringify({value: null});
    }
    if (operation === 'clear') {
        localStorage.clear();
        return JSON.stringify({value: null});
    }
    if (key !== null) {
        return JSON.stringify({value: localStorage.getItem(key)});
    }
    const out = Object.create(null);
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        out[k] = localStorage.getItem(k);
    }
    return JSON.stringify({value: out});
}"""


def _decode_storage_result(payload: str, origin: str) -> str | dict[str, str] | None:
    result = json.loads(payload)
    if result.get("mismatch"):
        raise InvalidParamsError(
            f"Origin mismatch: requested {origin!r} but page landed on {result['origin']!r} (likely redirect)"
        )
    return cast("str | dict[str, str] | None", result["value"])


async def _storage_in_origin(
    context: BrowserContext,
    origin: str,
    operation: Literal["get", "set", "clear"],
    *,
    mgr: InstanceManager,
    instance: str,
    key: str | None = None,
    items: dict[str, str] | None = None,
) -> str | dict[str, str] | None:
    """Check the browser-canonical origin and touch storage in the same JS turn."""
    page = await context.new_page()
    failed = False
    try:
        mark_operation_started(mgr.get(instance).instance_id, page_id=mgr.page_id(instance, page))
        await mgr.ensure_page_headers(mgr.get(instance), page)
        await page.goto(origin, wait_until="commit")
        # Playwright drops __proto__ object properties at its JS serialization
        # boundary. JSON text preserves arbitrary storage keys in both directions.
        return _decode_storage_result(
            await page.evaluate(
                _STORAGE_OPERATION,
                {"origin": origin, "operation": operation, "key": key, "items": json.dumps(items)},
            ),
            origin,
        )
    except BaseException:
        failed = True
        raise
    finally:
        try:
            with anyio.CancelScope(shield=True), anyio.fail_after(_STORAGE_CLOSE_TIMEOUT_SECONDS):
                await page.close()
        except Exception:
            if not failed:
                raise
            logger.warning("Temporary storage page cleanup failed after an operation failure", exc_info=True)


def _register_browser_get_cookies(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_get_cookies(
        instance: str,
        urls: list[str] | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Return cookies stored in the instance, optionally filtered by URL and name.

        urls is a list of full URLs (e.g. ["https://example.com"]). When provided,
        only cookies applicable to those URLs are returned (matching domain/path rules).
        When omitted, all cookies in the instance are returned. When ``name`` is
        given, the result is further filtered to cookies whose ``name`` matches
        exactly — an empty list is returned if none match (this is not an error).

        Returns on success:
            data: {"cookies": [{"name": str, "value": str, "domain": str,
                                 "path": str, "expires": float, "httpOnly": bool,
                                 "secure": bool, "sameSite": str}, ...]}

        Errors:
            instance_not_found — instance does not exist
        """
        try:
            rec = mgr.get(instance)
            ctx = rec.context
            async with mgr.lock_for(instance):
                if urls is not None:
                    cookies = await ctx.cookies(urls)
                else:
                    cookies = await ctx.cookies()
            if name is not None:
                cookies = [c for c in cookies if c.get("name") == name]
            return success_response(instance, data={"cookies": cookies})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except (PlaywrightError, OSError, RuntimeError, ValueError, TypeError) as e:
            return error_response(instance, "internal_error", str(e))


def _register_browser_set_cookies(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_set_cookies(
        instance: str, cookies: list[dict[str, Any]], *, page_id: str | None = None
    ) -> dict[str, Any]:
        """Add or update cookies on the instance using Playwright cookie format.

        Each cookie dict must have at minimum: name, value. Playwright also
        requires either ``domain`` (with ``path``) OR ``url`` to identify
        which site the cookie belongs to — supplying either is fine. When
        both are omitted, the instance's active page hostname is used as a
        default ``domain`` (if a page exists).
        Optional fields: path (default "/"), expires (Unix timestamp), httpOnly,
        secure, sameSite ("Strict"|"Lax"|"None").

        Returns on success:
            data: {"set_count": int}  — number of cookies applied

        Errors:
            instance_not_found — instance does not exist
            invalid_params     — cookie has neither domain nor url and no
                                 active page exists to default from

        Cookies set here affect all pages in the instance immediately.
        """
        try:
            rec = mgr.get(instance)
            ctx = rec.context
            async with mgr.lock_for(instance):
                default_domain: str | None = None
                if ctx.pages or page_id is not None:
                    active_page = await mgr.target_page(instance, page_id)
                    parsed = urlparse(active_page.url)
                    default_domain = parsed.hostname
                processed: list[dict[str, Any]] = []
                for cookie in cookies:
                    normalized = cookie
                    has_domain = bool(normalized.get("domain"))
                    has_url = bool(normalized.get("url"))
                    if not has_domain and not has_url:
                        if default_domain is None:
                            return error_response(
                                instance,
                                "invalid_params",
                                f"cookie {normalized.get('name')!r} has neither "
                                "domain nor url, and no active page to default from",
                            )
                        normalized = {**normalized, "domain": default_domain}
                    if "path" not in normalized and not normalized.get("url"):
                        normalized = {**normalized, "path": "/"}
                    processed.append(normalized)
                await ctx.add_cookies(cast("Sequence[SetCookieParam]", processed))
            return success_response(instance, data={"set_count": len(processed)})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except (PlaywrightError, OSError, RuntimeError, ValueError, TypeError) as e:
            return error_response(instance, "internal_error", str(e))


def _register_browser_clear_cookies(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_clear_cookies(instance: str) -> dict[str, Any]:
        """Remove all cookies from the instance.

        All cookies across all domains are deleted. Pages currently loaded
        in the instance are not reloaded — the deletion takes effect on the
        next request that would send cookies.

        Returns on success:
            data: {"cleared": True}

        Errors:
            instance_not_found — instance does not exist
        """
        try:
            rec = mgr.get(instance)
            ctx = rec.context
            async with mgr.lock_for(instance):
                await ctx.clear_cookies()
            return success_response(instance, data={"cleared": True})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except (PlaywrightError, OSError, RuntimeError, ValueError, TypeError) as e:
            return error_response(instance, "internal_error", str(e))


def _register_browser_get_local_storage(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_get_local_storage(
        instance: str,
        origin: str,
        key: str | None = None,
    ) -> dict[str, Any]:
        """Read localStorage for the given origin.

        Opens a temporary page that navigates to origin, reads localStorage,
        then closes — the instance's active page is not disturbed.
        Storage is accessed after the document commits, without waiting for
        DOMContentLoaded or site initialization scripts.
        origin must be a fully-qualified URL including scheme (e.g. "https://example.com").
        When ``key`` is provided, only the value for that key is returned
        (``None`` if the key does not exist).

        Returns on success:
            When key is None:
                data: {"items": {"key": "value", ...}, "origin": str}
            When key is given:
                data: {"key": str, "value": str | None, "origin": str}

        Errors:
            instance_not_found — instance does not exist
            internal_error    — navigation to origin failed (e.g. network error)
        """
        try:
            rec = mgr.get(instance)
            ctx = rec.context
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                value = await _storage_in_origin(ctx, origin, "get", mgr=mgr, instance=instance, key=key)
            if key is not None:
                return success_response(instance, data={"key": key, "value": value, "origin": origin})
            return success_response(instance, data={"items": value, "origin": origin})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_get_local_storage failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_set_local_storage(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_set_local_storage(instance: str, origin: str, items: dict[str, str]) -> dict[str, Any]:
        """Set localStorage key-value pairs for the given origin.

        Opens a temporary page that navigates to origin, sets each item via
        localStorage.setItem, then closes — the instance's active page is not disturbed.
        Storage is accessed after the document commits, without waiting for
        DOMContentLoaded or site initialization scripts.
        All values must be strings (localStorage only stores strings).

        Returns on success:
            data: {"set_count": int, "origin": str}

        Errors:
            instance_not_found — instance does not exist
            internal_error    — navigation to origin failed
        """
        try:
            rec = mgr.get(instance)
            ctx = rec.context
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                await _storage_in_origin(ctx, origin, "set", mgr=mgr, instance=instance, items=items)
            return success_response(
                instance,
                data={"set_count": len(items), "origin": origin},
            )
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_set_local_storage failed")
            return error_response(instance, "internal_error", str(e))


def _register_browser_clear_local_storage(mcp: FastMCP, mgr: InstanceManager) -> None:

    @mcp.tool
    async def browser_clear_local_storage(
        instance: str,
        origin: str | None = None,
        *,
        page_id: str | None = None,
    ) -> dict[str, Any]:
        """Clear localStorage entries.

        When ``origin`` is provided, opens a temporary page that navigates
        to origin, calls localStorage.clear(), then closes — the instance's
        active page is not disturbed. ``origin`` must be a fully-qualified
        URL including scheme.
        Storage is accessed after the document commits, without waiting for
        DOMContentLoaded or site initialization scripts.

        When ``origin`` is omitted, localStorage is cleared on the active
        page directly (no temp page, no navigation). Use this shortcut when
        you are already on the origin whose storage you want to clear.

        Returns on success:
            data: {"cleared": True, "origin": str}  — the origin URL that was cleared

        Errors:
            instance_not_found — instance does not exist
            internal_error    — navigation to origin failed
        """
        if origin is not None and page_id is not None:
            return error_response(instance, "invalid_params", "origin and page_id cannot be combined")
        try:
            rec = mgr.get(instance)
            ctx = rec.context
            async with mgr.lock_for(instance):
                assert_no_modal(mgr, instance)
                if origin is None:
                    page = await mgr.target_page(instance, page_id)
                    await page.evaluate("() => localStorage.clear()")
                    return success_response(instance, data={"cleared": True, "origin": page.url})
                await _storage_in_origin(ctx, origin, "clear", mgr=mgr, instance=instance)
            return success_response(instance, data={"cleared": True, "origin": origin})
        except BrowserMcpError as e:
            return error_response(instance, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_clear_local_storage failed")
            return error_response(instance, "internal_error", str(e))


def register(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register cookie and web storage tools on the MCP server."""
    _register_browser_get_cookies(mcp, mgr)
    _register_browser_set_cookies(mcp, mgr)
    _register_browser_clear_cookies(mcp, mgr)
    _register_browser_get_local_storage(mcp, mgr)
    _register_browser_set_local_storage(mcp, mgr)
    _register_browser_clear_local_storage(mcp, mgr)
