"""InstanceManager: named registry of isolated Camoufox browser instances.

Each entry is an InstanceRecord owning its own AsyncCamoufox process, one
BrowserContext, a per-instance asyncio.Lock, and per-instance bookkeeping
(console/network/modal state, active tab index). The manager serializes
create/destroy via a registry lock; individual tool ops serialize on the
per-instance lock so different instances run in parallel.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .errors import (
    InstanceAlreadyExistsError,
    InstanceLimitExceededError,
    InstanceNotFoundError,
    InvalidParamsError,
    ModalStateBlockedError,
    ProfileDirInUseError,
)
from .instance import InstanceRecord, InstanceState, launch_instance

if TYPE_CHECKING:
    from playwright.async_api import (
        BrowserContext,
        Dialog,
        FileChooser,
        Page,
        Request,
        Response,
        SourceLocation,
    )

    from .config import BrowserServerConfig

logger = logging.getLogger(__name__)


def summarize_instance(rec: InstanceRecord) -> dict[str, Any]:
    """Build the public InstanceSummary dict for a single record.

    Shared between InstanceManager.list() and tool-layer wrappers so the
    summary shape stays in one place.
    """
    pages = rec.context.pages
    if pages:
        idx = rec.state.active_page_index
        if idx < 0 or idx >= len(pages):
            idx = 0
        active_url = pages[idx].url
    else:
        active_url = None
    return {
        "name": rec.name,
        "mode": "persistent" if rec.profile_dir is not None else "ephemeral",
        "profile_dir": rec.profile_dir,
        "page_count": len(pages),
        "active_url": active_url,
        "created_at": rec.created_at.isoformat(),
    }


def _format_console_location(loc: SourceLocation | None) -> str | None:
    if not loc:
        return None
    url = loc.get("url") or ""
    if not url:
        return None
    line = loc.get("lineNumber", 0)
    col = loc.get("columnNumber", 0)
    return f"{url}:{line}:{col}"


class InstanceManager:
    """Named registry of isolated Camoufox instances."""

    def __init__(self, config: BrowserServerConfig) -> None:
        """Initialize an empty registry bound to the given server configuration."""
        self._instances: dict[str, InstanceRecord] = {}
        self._registry_lock = asyncio.Lock()
        self._max = config.max_instances

    async def create(
        self,
        name: str,
        *,
        profile_dir: str | None = None,
        headless: bool | Literal["virtual"] = True,
        proxy: dict[str, str] | None = None,
        humanize: bool | float = True,
        window: tuple[int, int] | None = None,
    ) -> InstanceRecord:
        """Create and register a new named Camoufox instance.

        Preflight order: name-collision → limit → profile_dir-collision → launch.
        Raises InstanceAlreadyExistsError, InstanceLimitExceededError, or
        ProfileDirInUseError before touching Playwright if a preflight fails.
        """
        async with self._registry_lock:
            if name in self._instances:
                raise InstanceAlreadyExistsError(f"Instance {name!r} already exists.")
            if len(self._instances) >= self._max:
                raise InstanceLimitExceededError(
                    f"Cannot create instance {name!r}: limit of {self._max} reached. "
                    f"Destroy an existing instance first."
                )
            if profile_dir is not None:
                # Path.resolve() is pure normalization here (strict=False, no I/O on
                # missing paths); the ASYNC240 suppression is intentional and safe.
                normalized = Path(profile_dir).resolve()  # noqa: ASYNC240
                for r in self._instances.values():
                    if r.profile_dir is not None and Path(r.profile_dir).resolve() == normalized:  # noqa: ASYNC240
                        raise ProfileDirInUseError(
                            f"Cannot create instance {name!r}: profile_dir {profile_dir!r} is "
                            f"already in use by instance {r.name!r}. Destroy it first or choose "
                            f"a different profile_dir."
                        )

            stack, ctx = await launch_instance(
                profile_dir=profile_dir,
                headless=headless,
                proxy=proxy,
                humanize=humanize,
                window=window,
            )

            state = InstanceState()
            self._wire_event_listeners(ctx, state)
            self._wire_modal_listeners(ctx, state)

            record = InstanceRecord(
                name=name,
                stack=stack,
                context=ctx,
                lock=asyncio.Lock(),
                state=state,
                profile_dir=profile_dir,
                created_at=datetime.now(tz=UTC),
            )
            self._instances[name] = record
            logger.info("Created instance %r (mode=%s)", name, "persistent" if profile_dir else "ephemeral")
            return record

    async def get(self, name: str) -> InstanceRecord:
        """Look up an instance by name. Raises InstanceNotFoundError if missing."""
        rec = self._instances.get(name)
        if rec is None:
            raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
        return rec

    def lock_for(self, name: str) -> asyncio.Lock:
        """Return the per-instance lock for serializing tool operations."""
        rec = self._instances.get(name)
        if rec is None:
            raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
        return rec.lock

    def state(self, name: str) -> InstanceState:
        """Return the InstanceState for a named instance."""
        rec = self._instances.get(name)
        if rec is None:
            raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
        return rec.state

    def list_names(self) -> list[str]:
        """Return the names of all active instances."""
        return list(self._instances.keys())

    async def destroy(self, name: str) -> None:
        """Close and remove a named instance from the registry.

        Acquires both the registry lock and the per-instance lock so that any
        in-flight tool operation on this instance completes before teardown.
        """
        async with self._registry_lock:
            rec = self._instances.get(name)
            if rec is None:
                raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
            async with rec.lock:
                await rec.stack.aclose()
                del self._instances[name]
            logger.info("Destroyed instance %r", name)

    async def list(self) -> list[dict[str, Any]]:
        """Return summary info for all active instances."""
        snapshot = list(self._instances.items())
        return [summarize_instance(rec) for _, rec in snapshot]

    async def active_page(self, name: str) -> Page:
        """Return the active page for an instance, creating one if none exist."""
        rec = await self.get(name)
        if not rec.context.pages:
            page = await rec.context.new_page()
            rec.state.active_page_index = 0
            return page
        idx = rec.state.active_page_index
        if idx < 0 or idx >= len(rec.context.pages):
            idx = 0
            rec.state.active_page_index = 0
        return rec.context.pages[idx]

    def set_active_page(self, name: str, index: int) -> None:
        """Set which tab is the logical active page for an instance."""
        rec = self._instances.get(name)
        if rec is None:
            raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
        if index < 0 or index >= len(rec.context.pages):
            raise InvalidParamsError(f"tab index {index} out of range (have {len(rec.context.pages)} pages)")
        rec.state.active_page_index = index

    def get_modal_states(self, name: str) -> list[dict[str, Any]]:
        """Return the list of pending modal states for an instance.

        Entries whose page has closed are pruned automatically.
        """
        rec = self._instances.get(name)
        if rec is None:
            raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
        states = rec.state.modal_states
        states[:] = [s for s in states if not s["page"].is_closed()]
        return list(states)

    def consume_modal_state(self, name: str, kind: str) -> dict[str, Any] | None:
        """Pop and return the oldest pending modal of the given kind, or None."""
        rec = self._instances.get(name)
        if rec is None:
            raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
        states = rec.state.modal_states
        for i, state in enumerate(states):
            if state["kind"] == kind:
                return states.pop(i)
        return None

    async def shutdown_all(self) -> None:
        """Close every instance in parallel; drain in-flight creates first.

        Acquires the registry lock so a concurrent create() call must either
        complete (and its record gets closed by this shutdown) or block until
        the registry is cleared. Without this guard, a create() that has passed
        preflight but is still awaiting launch_instance() could insert a fresh
        record AFTER shutdown_all has read the keys, leaking a live Camoufox.
        """
        async with self._registry_lock:
            names = list(self._instances.keys())
            results = await asyncio.gather(
                *(self._close_one(n) for n in names),
                return_exceptions=True,
            )
            for n, r in zip(names, results, strict=False):
                if isinstance(r, BaseException):
                    logger.warning("Error closing instance %r on shutdown: %s", n, r)
            self._instances.clear()

    async def _close_one(self, name: str) -> None:
        rec = self._instances[name]
        async with rec.lock:
            await rec.stack.aclose()

    def _wire_event_listeners(self, ctx: BrowserContext, state: InstanceState) -> None:
        def _on_request(req: Request) -> None:
            entry = {
                "_id": id(req),
                "url": req.url,
                "method": req.method,
                "status": None,
                "resource_type": req.resource_type,
                "failure": None,
            }
            state.network_requests.append(entry)
            state.network_request_index[id(req)] = entry

        def _on_response(response: Response) -> None:
            entry = state.network_request_index.get(id(response.request))
            if entry is not None:
                entry["status"] = response.status

        def _on_requestfailed(request: Request) -> None:
            entry = state.network_request_index.get(id(request))
            if entry is not None:
                entry["failure"] = request.failure or "unknown"

        def _attach(page: Page) -> None:
            page.on(
                "console",
                lambda msg: state.console_messages.append(
                    {
                        "type": msg.type,
                        "text": msg.text,
                        "location": _format_console_location(msg.location),
                    }
                ),
            )
            page.on(
                "pageerror",
                lambda exc: state.console_messages.append({"type": "error", "text": str(exc), "location": None}),
            )
            page.on("request", _on_request)
            page.on("response", _on_response)
            page.on("requestfailed", _on_requestfailed)

        ctx.on("page", _attach)
        for existing_page in ctx.pages:
            _attach(existing_page)

    def _wire_modal_listeners(self, ctx: BrowserContext, state: InstanceState) -> None:
        def _on_dialog(page: Page, dialog: Dialog) -> None:
            state.modal_states.append({"kind": "dialog", "object": dialog, "page": page})

        def _on_filechooser(page: Page, file_chooser: FileChooser) -> None:
            state.modal_states.append({"kind": "filechooser", "object": file_chooser, "page": page})

        def _attach(page: Page) -> None:
            page.on("dialog", lambda dialog: _on_dialog(page, dialog))
            page.on("filechooser", lambda fc: _on_filechooser(page, fc))

        ctx.on("page", _attach)
        for existing_page in ctx.pages:
            _attach(existing_page)


def assert_no_modal(mgr: InstanceManager, instance: str) -> None:
    """Raise ModalStateBlockedError if any dialog or file-chooser is pending."""
    states = mgr.get_modal_states(instance)
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
