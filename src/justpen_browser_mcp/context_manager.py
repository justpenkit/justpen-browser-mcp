"""ContextManager: named-context registry within a single Camoufox browser.

Hosts multiple BrowserContext objects in one browser, each addressed by
agent-defined name. Per-context asyncio.Locks serialize operations within
a context while different contexts run in parallel.

Lifecycle:
    create(name)        — registers a new context, lazy-launches browser
    get(name)           — looks up by name
    destroy(name)       — closes context, frees lock; auto-shuts-down
                          browser if no contexts remain
    list()              — returns summary of all active contexts
    active_page(name)   — returns active page (creates one if none exist)

State I/O (export_state, load_state) is in Part 2 — added in the next task.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import (
        BrowserContext,
        Dialog,
        FileChooser,
        Page,
        Request,
        Response,
    )

    from .camoufox import CamoufoxLauncher

from .errors import (
    ContextAlreadyExistsError,
    ContextNotFoundError,
    InvalidParamsError,
    InvalidStateFileError,
    ModalStateBlockedError,
    StateFileNotFoundError,
)

logger = logging.getLogger(__name__)


def _format_console_location(loc: object) -> str | None:
    """Format a Playwright console message location dict into 'url:line:col'.

    Playwright Python returns a dict like
    ``{"url": str, "lineNumber": int, "columnNumber": int}``. Returns None when
    the location is missing, empty, or has no URL.
    """
    if not loc:
        return None
    if not isinstance(loc, dict):
        return None
    url = loc.get("url") or ""
    if not url:
        return None
    line = loc.get("lineNumber", 0)
    col = loc.get("columnNumber", 0)
    return f"{url}:{line}:{col}"


class ContextManager:
    """Named registry of BrowserContexts within a single Camoufox browser."""

    def __init__(self, launcher: CamoufoxLauncher) -> None:
        self._launcher = launcher
        self._contexts: dict[str, BrowserContext] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def create(self, name: str, state_path: str | None = None) -> BrowserContext:
        """Create a new BrowserContext, optionally pre-loading storage_state."""
        async with self._registry_lock:
            if name in self._contexts:
                raise ContextAlreadyExistsError(f"Context '{name}' already exists. Call browser_destroy_context first.")

            browser = await self._launcher.get_browser()

            kwargs: dict = {}
            if state_path is not None:
                kwargs["storage_state"] = self._load_state_file(state_path)

            ctx = await browser.new_context(**kwargs)

            # Initialize event capture buffers for the inspection tools.
            ctx._console_messages = []
            ctx._network_requests = []
            # O(1) lookup index: maps request object id → list entry
            ctx._network_request_index = {}
            # Track which tab (by index) is the logical "active" page for
            # subsequent tool calls. Updated by browser_tabs(select/close/new).
            ctx._active_page_index = 0

            def _on_request(req: Request) -> None:
                entry = {
                    "_id": id(req),
                    "url": req.url,
                    "method": req.method,
                    "status": None,
                    "resource_type": req.resource_type,
                    "failure": None,
                }
                ctx._network_requests.append(entry)
                ctx._network_request_index[id(req)] = entry

            def _on_response(response: Response) -> None:
                entry = ctx._network_request_index.get(id(response.request))
                if entry is not None:
                    entry["status"] = response.status

            def _on_requestfailed(request: Request) -> None:
                entry = ctx._network_request_index.get(id(request))
                if entry is not None:
                    entry["failure"] = request.failure or "unknown"

            def _attach_page_listeners(page: Page) -> None:
                page.on(
                    "console",
                    lambda msg: ctx._console_messages.append(
                        {
                            "type": msg.type,
                            "text": msg.text,
                            "location": _format_console_location(msg.location),
                        }
                    ),
                )
                page.on(
                    "pageerror",
                    lambda exc: ctx._console_messages.append(
                        {
                            "type": "error",
                            "text": str(exc),
                            "location": None,
                        }
                    ),
                )
                page.on("request", _on_request)
                page.on("response", _on_response)
                page.on("requestfailed", _on_requestfailed)

            ctx.on("page", _attach_page_listeners)
            for existing_page in ctx.pages:
                _attach_page_listeners(existing_page)

            # Initialize modal state tracking (CC-1, CC-2, CC-3 from 2026-04-08 audit).
            # When a dialog or file-chooser appears, store it on the context so
            # tools can either consume it (browser_handle_dialog, browser_file_upload)
            # or refuse to execute (assert_no_modal guard).
            ctx._modal_states = []  # list of {"kind": str, "object": Dialog|FileChooser, "page": Page}

            def _on_dialog(page: Page, dialog: Dialog) -> None:
                ctx._modal_states.append({"kind": "dialog", "object": dialog, "page": page})

            def _on_filechooser(page: Page, file_chooser: FileChooser) -> None:
                ctx._modal_states.append({"kind": "filechooser", "object": file_chooser, "page": page})

            def _attach_modal_listeners(page: Page) -> None:
                page.on("dialog", lambda dialog: _on_dialog(page, dialog))
                page.on("filechooser", lambda fc: _on_filechooser(page, fc))

            # Wire to all current and future pages
            ctx.on("page", _attach_modal_listeners)
            for existing_page in ctx.pages:
                _attach_modal_listeners(existing_page)

            self._contexts[name] = ctx
            self._locks[name] = asyncio.Lock()
            if state_path:
                logger.info("Created context %r with state from %s", name, state_path)
            else:
                logger.info("Created context %r", name)
            return ctx

    async def get(self, name: str) -> BrowserContext:
        """Look up a context by name. Raises ContextNotFoundError if missing."""
        ctx = self._contexts.get(name)
        if ctx is None:
            raise ContextNotFoundError(f"Context '{name}' does not exist. Call browser_create_context first.")
        return ctx

    def lock_for(self, name: str) -> asyncio.Lock:
        """Per-context lock for serializing tool operations on a context."""
        if name not in self._locks:
            raise ContextNotFoundError(f"Context '{name}' does not exist.")
        return self._locks[name]

    async def destroy(self, name: str) -> None:
        """Close a context and remove it from the registry.

        Acquires both the registry lock and the per-context lock so that
        any in-flight tool operation on this context completes before
        the context is closed. If this was the last context, auto-shuts-
        down the underlying Camoufox browser.
        """
        async with self._registry_lock:
            if name not in self._contexts:
                raise ContextNotFoundError(f"Context '{name}' does not exist.")

            # Drain in-flight ops by acquiring the per-context lock. Any
            # tool currently holding this lock will complete before we
            # proceed to close the context.
            per_context_lock = self._locks[name]
            async with per_context_lock:
                await self._contexts[name].close()
                del self._contexts[name]
                del self._locks[name]
            logger.info("Destroyed context %r", name)

            if not self._contexts:
                logger.info("No contexts remaining, shutting down Camoufox browser")
                await self._launcher.shutdown()

    async def list(self) -> list[dict]:
        """Return summary info for all active contexts.

        The dict is snapshotted before iteration so that concurrent
        create/destroy calls cannot mutate it mid-loop (which would raise
        ``RuntimeError: dictionary changed size during iteration``).
        Individual contexts that fail to report cookies (typically because
        they were destroyed mid-iteration) are skipped silently.
        """
        snapshot = list(self._contexts.items())
        result = []
        for name, ctx in snapshot:
            try:
                cookies = await ctx.cookies()
            except Exception:
                # Context was destroyed concurrently; skip it.
                continue
            pages = ctx.pages
            if pages:
                idx = getattr(ctx, "_active_page_index", 0)
                if idx < 0 or idx >= len(pages):
                    idx = 0
                active_url = pages[idx].url
            else:
                active_url = None
            result.append(
                {
                    "context": name,
                    "page_count": len(pages),
                    "active_url": active_url,
                    "cookie_count": len(cookies),
                }
            )
        return result

    async def active_page(self, name: str) -> Page:
        """Return the active page for a context, creating one if none exist.

        Honors the per-context ``_active_page_index`` set by browser_tabs
        (select/new/close). If the stored index is out of range, it is
        clamped to 0 so subsequent calls remain consistent.
        """
        ctx = await self.get(name)
        if not ctx.pages:
            page = await ctx.new_page()
            ctx._active_page_index = 0
            return page
        idx = getattr(ctx, "_active_page_index", 0)
        if idx < 0 or idx >= len(ctx.pages):
            idx = 0
            ctx._active_page_index = 0
        return ctx.pages[idx]

    def set_active_page(self, name: str, index: int) -> None:
        """Set which tab is the logical active page for a context.

        Raises ContextNotFoundError if the context does not exist, and
        InvalidParamsError if ``index`` is out of range for the current
        pages list.
        """
        ctx = self._contexts.get(name)
        if ctx is None:
            raise ContextNotFoundError(f"Context '{name}' does not exist.")
        if index < 0 or index >= len(ctx.pages):
            raise InvalidParamsError(f"tab index {index} out of range (have {len(ctx.pages)} pages)")
        ctx._active_page_index = index

    async def export_state(self, name: str, state_path: str) -> None:
        """Dump the context's current cookies + localStorage to a JSON file.

        Creates parent directories if missing. Caller-supplied path is
        absolute (the MCP server is path-agnostic).
        """
        ctx = await self.get(name)
        state = await ctx.storage_state()
        path = Path(state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2))
        logger.info("Exported state for %r to %s", name, state_path)

    async def load_state(self, name: str, state_path: str) -> None:
        """Replace the context's cookies + localStorage with state from a file.

        Implementation detail: clears existing cookies, adds new cookies,
        then for each origin in 'origins', opens a temporary page on the
        origin and uses page.evaluate() to set localStorage entries. The
        temporary page is closed afterwards. This is more invasive than
        constructing a fresh context with storage_state, but it preserves
        the BrowserContext object reference, enabling mid-session resets
        without invalidating refs/state held by callers.
        """
        ctx = await self.get(name)
        state = self._load_state_file(state_path)

        # Capture previous origins that have localStorage so we can clear any
        # that are omitted from (or empty in) the new state file. Without this
        # step, load_state silently preserves stale localStorage on origins
        # not mentioned by the new file — contradicting the "replace" contract.
        prev_state = await ctx.storage_state()
        prev_origins = {o["origin"] for o in prev_state.get("origins", []) if o.get("localStorage")}

        # Validate cookies and origins structure before mutating any state,
        # so a malformed file cannot leave the context in a half-applied state.
        for cookie in state.get("cookies", []):
            if not isinstance(cookie, dict) or "name" not in cookie or "value" not in cookie:
                raise InvalidStateFileError("Each cookie must be a dict with at least 'name' and 'value' keys")
            if "url" not in cookie and "domain" not in cookie:
                raise InvalidStateFileError(
                    f"Cookie {cookie.get('name')!r} needs 'url' or 'domain' for Playwright to accept it"
                )

        # Validate origins structure.
        for origin_data in state.get("origins", []):
            if not isinstance(origin_data, dict) or "origin" not in origin_data:
                raise InvalidStateFileError("Each entry in 'origins' must be a dict with an 'origin' key")
            local_storage = origin_data.get("localStorage", [])
            if not isinstance(local_storage, list):
                raise InvalidStateFileError(f"'localStorage' for origin {origin_data['origin']!r} must be a list")
            for item in local_storage:
                if not isinstance(item, dict) or "name" not in item or "value" not in item:
                    raise InvalidStateFileError("Each localStorage item must have 'name' and 'value' keys")

        await ctx.clear_cookies()
        if state.get("cookies"):
            await ctx.add_cookies(state["cookies"])

        new_origins_with_data: set[str] = set()
        failed_origins: list[str] = []
        for origin_data in state.get("origins", []):
            origin = origin_data["origin"]
            local_storage = origin_data.get("localStorage", [])
            if not local_storage:
                continue
            page = await ctx.new_page()
            try:
                await page.goto(origin)
                # Verify page didn't redirect to a different origin.
                actual_parts = page.url.rstrip("/").split("/", 3)[:3]
                expected_parts = origin.rstrip("/").split("/", 3)[:3]
                if actual_parts != expected_parts:
                    logger.warning(
                        "load_state: origin %r redirected to %r, skipping localStorage",
                        origin,
                        page.url,
                    )
                    failed_origins.append(origin)
                else:
                    js_items = json.dumps([{"name": item["name"], "value": item["value"]} for item in local_storage])
                    await page.evaluate(
                        f"localStorage.clear(); "
                        f"const items = {js_items}; "
                        f"items.forEach(i => localStorage.setItem(i.name, i.value));"
                    )
                    new_origins_with_data.add(origin)
            except Exception as exc:
                logger.warning(
                    "load_state: failed to set localStorage for origin %r: %s",
                    origin,
                    exc,
                )
                # Preserve old localStorage: prevent stale-origin cleanup
                # from clearing data that was working before this call.
                new_origins_with_data.add(origin)
                failed_origins.append(origin)
            finally:
                await page.close()

        # Clear localStorage on any origin that had data before but is not in
        # the new state (or is present with an empty list).
        for stale_origin in prev_origins - new_origins_with_data:
            page = await ctx.new_page()
            try:
                await page.goto(stale_origin)
                actual_parts = page.url.rstrip("/").split("/", 3)[:3]
                expected_parts = stale_origin.rstrip("/").split("/", 3)[:3]
                if actual_parts != expected_parts:
                    logger.warning(
                        "load_state: stale origin %r redirected to %r, skipping clear",
                        stale_origin,
                        page.url,
                    )
                else:
                    await page.evaluate("() => localStorage.clear()")
            finally:
                await page.close()

        logger.info("Loaded state for %r from %s", name, state_path)
        return failed_origins

    def get_modal_states(self, name: str) -> list[dict]:
        """Return the list of pending modal states for a context.

        Each entry is {"kind": "dialog"|"filechooser", "object": Dialog|FileChooser, "page": Page}.
        Empty list means no modals are pending. Entries whose page has
        closed are pruned automatically so they cannot block future tools.
        """
        ctx = self._contexts.get(name)
        if ctx is None:
            raise ContextNotFoundError(f"Context '{name}' does not exist.")
        states = getattr(ctx, "_modal_states", [])
        # Prune entries from closed pages so stale modals don't block tools.
        states[:] = [s for s in states if not s["page"].is_closed()]
        return list(states)

    def consume_modal_state(self, name: str, kind: str) -> dict | None:
        """Pop and return the oldest pending modal of the given kind.

        Used by browser_handle_dialog (kind='dialog') and browser_file_upload
        (kind='filechooser') to retrieve and acknowledge the pending modal.
        Returns None if no modal of that kind is pending.
        """
        ctx = self._contexts.get(name)
        if ctx is None:
            raise ContextNotFoundError(f"Context '{name}' does not exist.")
        states = getattr(ctx, "_modal_states", [])
        for i, state in enumerate(states):
            if state["kind"] == kind:
                return states.pop(i)
        return None

    def _load_state_file(self, state_path: str) -> dict:
        """Read and validate a Playwright storage_state JSON file."""
        path = Path(state_path)
        if not path.exists():
            raise StateFileNotFoundError(f"State file not found: {state_path}")
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise InvalidStateFileError(f"Invalid JSON in state file: {e}")
        if not isinstance(data, dict) or "cookies" not in data:
            raise InvalidStateFileError(
                "State file does not look like a Playwright storage_state JSON: missing 'cookies' key"
            )
        return data


def assert_no_modal(ctx_mgr: ContextManager, context: str) -> None:
    """Raise ModalStateBlockedError if any dialog or file-chooser is pending.

    Tool dispatch handlers call this BEFORE executing any Playwright action
    that would interact with a blocked page. Tools that legitimately consume
    modal state (browser_handle_dialog, browser_file_upload) skip this guard
    and call ctx_mgr.consume_modal_state() instead.
    """
    states = ctx_mgr.get_modal_states(context)
    if not states:
        return
    state = states[0]
    kind = state["kind"]
    if kind == "dialog":
        dialog = state["object"]
        msg = (
            f"A {dialog.type!r} dialog is currently open with message "
            f"{dialog.message!r}. Call browser_handle_dialog to dismiss it "
            f"before issuing other tools."
        )
    elif kind == "filechooser":
        msg = (
            "A file-chooser dialog is pending. Call browser_file_upload "
            "with the desired paths before issuing other tools."
        )
    else:
        msg = f"A {kind} modal state is pending; resolve it before continuing."
    raise ModalStateBlockedError(msg)
