"""InstanceManager: named registry of isolated Camoufox browser instances.

Each entry is an InstanceRecord owning its own AsyncCamoufox process, one
BrowserContext, a per-instance asyncio.Lock, and per-instance bookkeeping
(console/network/modal state, active tab index). The manager serializes
create/destroy via a registry lock; individual tool ops serialize on the
per-instance lock so different instances run in parallel.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from anyio import Path as AsyncPath

from .errors import (
    InstanceAlreadyExistsError,
    InstanceCrashedError,
    InstanceLimitExceededError,
    InstanceNotFoundError,
    InternalError,
    InvalidParamsError,
    ModalStateBlockedError,
    OperationTimeoutError,
    ProfileDirInUseError,
)
from .events import EventBuffer
from .instance import InstanceRecord, InstanceState, launch_instance
from .operation_context import mark_operation_started

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from playwright.async_api import (
        Browser,
        BrowserContext,
        ConsoleMessage,
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
    active_url: str | None = None
    page_count = 0
    try:
        pages = rec.context.pages
        page_count = len(pages)
        if pages:
            selected = _existing_active_page(rec)
            active_url = selected.url if selected is not None else None
    except Exception:  # noqa: BLE001 — a dead context must never break summaries
        active_url = None
    idle_seconds = (datetime.now(tz=UTC) - rec.state.last_used_at).total_seconds()
    return {
        "name": rec.name,
        "instance_id": rec.instance_id,
        "status": rec.state.status,
        "mode": "persistent" if rec.profile_dir is not None else "ephemeral",
        "profile_dir": rec.profile_dir,
        "page_count": page_count,
        "active_url": active_url,
        "idle_seconds": round(idle_seconds, 1),
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


@contextlib.asynccontextmanager
async def _operation(
    rec: InstanceRecord,
    lock: asyncio.Lock,
    validate: Callable[[InstanceRecord], None],
    timeout_seconds: float,
) -> AsyncGenerator[None]:
    """Track and bound one cooperative operation, including its lock wait."""
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("An instance operation requires an asyncio task")
    already_tracked = task in rec.operation_tasks
    rec.operation_tasks.add(task)
    deadline = asyncio.timeout(timeout_seconds)
    try:
        async with deadline, lock:
            validate(rec)
            mark_operation_started(rec.instance_id)
            _touch(rec)
            try:
                yield
            finally:
                _touch(rec)
    except TimeoutError as error:
        if deadline.expired():
            raise OperationTimeoutError(
                f"Instance {rec.name!r} operation exceeded {timeout_seconds:g} seconds."
            ) from error
        raise
    finally:
        if not already_tracked:
            rec.operation_tasks.discard(task)


def _touch(rec: InstanceRecord) -> None:
    rec.state.last_used_at = datetime.now(tz=UTC)
    rec.state.last_used_monotonic = monotonic()


def _existing_active_page(rec: InstanceRecord) -> Page | None:
    pages = rec.context.pages
    if not pages:
        return None
    if rec.state.active_page in pages:
        return rec.state.active_page
    index = max(0, min(rec.state.active_page_index, len(pages) - 1))
    return pages[index]


class InstanceManager:
    """Named registry of isolated Camoufox instances."""

    def __init__(self, config: BrowserServerConfig) -> None:
        """Initialize an empty registry bound to the given server configuration."""
        self._instances: dict[str, InstanceRecord] = {}
        self._registry_lock = asyncio.Lock()
        self._reservations: dict[str, str | None] = {}
        self._pending_creates: dict[str, asyncio.Task[InstanceRecord]] = {}
        self._abandoned_launches: set[asyncio.Task[InstanceRecord]] = set()
        self._retired: dict[str, InstanceRecord] = {}
        self._launch_cleanup: dict[str, dict[str, str]] = {}
        self._shutting_down = False
        self._shutdown_task: asyncio.Task[None] | None = None
        self._config = config
        self._max = config.max_instances
        self._closing_tasks: set[asyncio.Task[None]] = set()
        self._reaper_task: asyncio.Task[None] | None = None

    async def create(
        self,
        name: str,
        *,
        profile_dir: str | None = None,
        headless: bool | Literal["virtual"] | None = None,
        proxy: dict[str, str] | None = None,
        humanize: bool | float | None = None,
        window: tuple[int, int] | None = None,
        block_images: bool | None = None,
        block_webrtc: bool | None = None,
        block_webgl: bool | None = None,
        camoufox_os: tuple[str, ...] | None = None,
        locale: str | None = None,
        geoip: bool | None = None,
        firefox_user_prefs: dict[str, Any] | None = None,
        camoufox_args: tuple[str, ...] | None = None,
        enable_cache: bool | None = None,
        ff_version: int | None = None,
    ) -> InstanceRecord:
        """Create and register a new named Camoufox instance.

        Each camoufox-related parameter defaults to ``None``, meaning "use the
        server-level default from config"; a non-None value here overrides the
        server default for this instance only.

        Preflight order: name-collision → limit → profile_dir-collision → launch.
        Raises InstanceAlreadyExistsError, InstanceLimitExceededError, or
        ProfileDirInUseError before touching Playwright if a preflight fails.
        """
        cfg = self._config
        eff_headless = headless if headless is not None else cfg.headless
        eff_proxy = proxy if proxy is not None else cfg.proxy
        eff_humanize = humanize if humanize is not None else cfg.humanize
        eff_window = window if window is not None else cfg.window
        eff_block_images = block_images if block_images is not None else cfg.block_images
        eff_block_webrtc = block_webrtc if block_webrtc is not None else cfg.block_webrtc
        eff_block_webgl = block_webgl if block_webgl is not None else cfg.block_webgl
        eff_camoufox_os = camoufox_os if camoufox_os is not None else cfg.camoufox_os
        eff_locale = locale if locale is not None else cfg.locale
        eff_geoip = geoip if geoip is not None else cfg.geoip
        eff_firefox_user_prefs = firefox_user_prefs if firefox_user_prefs is not None else cfg.firefox_user_prefs
        eff_camoufox_args = camoufox_args if camoufox_args is not None else cfg.camoufox_args
        eff_enable_cache = enable_cache if enable_cache is not None else cfg.enable_cache
        eff_ff_version = ff_version if ff_version is not None else cfg.ff_version

        resolved_profile_dir = str(await AsyncPath(profile_dir).resolve()) if profile_dir is not None else None
        async with self._registry_lock:
            self._reserve(name, resolved_profile_dir)
            task = asyncio.create_task(
                self._launch_reserved(
                    name,
                    resolved_profile_dir,
                    partial(
                        launch_instance,
                        profile_dir=resolved_profile_dir,
                        headless=eff_headless,
                        proxy=eff_proxy,
                        humanize=eff_humanize,
                        window=eff_window,
                        block_images=eff_block_images,
                        block_webrtc=eff_block_webrtc,
                        block_webgl=eff_block_webgl,
                        camoufox_os=eff_camoufox_os,
                        locale=eff_locale,
                        geoip=eff_geoip,
                        firefox_user_prefs=eff_firefox_user_prefs,
                        camoufox_args=eff_camoufox_args,
                        enable_cache=eff_enable_cache,
                        ff_version=eff_ff_version,
                    ),
                ),
                name=f"launch-{name}",
            )
            self._pending_creates[name] = task
            task.add_done_callback(partial(self._launch_finished, name))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self._abandoned_launches.add(task)
            task.cancel()
            await asyncio.wait({task}, timeout=self._config.close_timeout_seconds)
            if task.done():
                self._abandoned_launches.discard(task)
                if not task.cancelled() and task.exception() is None:
                    await asyncio.shield(self._start_close(task.result()))
            raise

    def _reserve(self, name: str, profile_dir: str | None) -> None:
        if self._shutting_down:
            raise InvalidParamsError("Instance manager is shutting down; new instances cannot be created.")
        if name in self._reservations:
            raise InstanceAlreadyExistsError(f"Instance {name!r} already exists or is being created/closed.")
        if len(self._reservations) >= self._max:
            raise InstanceLimitExceededError(f"Cannot create instance {name!r}: limit of {self._max} reached.")
        if profile_dir is not None:
            for owner, reserved in self._reservations.items():
                if reserved == profile_dir:
                    raise ProfileDirInUseError(f"Profile {profile_dir!r} is already reserved by instance {owner!r}.")
        self._reservations[name] = profile_dir

    def _launch_finished(self, name: str, task: asyncio.Task[InstanceRecord]) -> None:
        self._abandoned_launches.discard(task)
        if self._pending_creates.get(name) is task:
            self._pending_creates.pop(name)
            if name not in self._instances and name not in self._retired and name not in self._launch_cleanup:
                self._reservations.pop(name, None)
        if not task.cancelled():
            task.exception()  # Retrieve failures even when the requesting client was cancelled.

    async def _launch_reserved(
        self,
        name: str,
        profile_dir: str | None,
        launch: Callable[..., Awaitable[tuple[AsyncExitStack, BrowserContext, Browser | None]]],
    ) -> InstanceRecord:
        owned_stack = AsyncExitStack()
        deadline = asyncio.timeout(self.operation_timeout_seconds)
        try:
            async with deadline:
                mark_operation_started(None)
                stack, ctx, browser = await launch(stack=owned_stack)
        except BaseException as error:
            self._launch_cleanup[name] = {"name": name, "status": "closing"}
            cleanup = asyncio.create_task(self._rollback_launch(name, owned_stack), name=f"rollback-{name}")
            self._track_close(cleanup)
            await asyncio.shield(cleanup)
            if isinstance(error, TimeoutError) and deadline.expired():
                raise OperationTimeoutError(f"Instance {name!r} launch exceeded its operation deadline.") from error
            raise
        record = InstanceRecord(
            name=name,
            stack=stack,
            context=ctx,
            lock=asyncio.Lock(),
            state=InstanceState(
                console_messages=EventBuffer(self.event_buffer_size),
                network_requests=EventBuffer(self.event_buffer_size),
            ),
            profile_dir=profile_dir,
            created_at=datetime.now(tz=UTC),
            browser=browser,
        )
        try:
            self._register_record(record)
        except BaseException:
            await asyncio.shield(self._start_close(record))
            raise
        return record

    async def _rollback_launch(self, name: str, stack: AsyncExitStack) -> None:
        """Keep ownership of allocations made before BrowserContext creation."""
        resource = asyncio.create_task(stack.aclose(), name=f"rollback-resources-{name}")
        self._track_close(resource)
        done, _ = await asyncio.wait({resource}, timeout=self._config.close_timeout_seconds)
        failed = not done or resource.cancelled()
        if done and not resource.cancelled():
            failed = resource.exception() is not None
        if failed:
            resource.cancel()
            self._launch_cleanup[name] = {
                "name": name,
                "status": "close_failed",
                "close_error": "Launch rollback failed or timed out; name/profile remain reserved until server restart.",
            }
            logger.error("Launch rollback failed for %r; reservation retained", name)
        else:
            self._launch_cleanup.pop(name, None)
            if name not in self._pending_creates:
                self._reservations.pop(name, None)

    def _register_record(self, record: InstanceRecord) -> None:
        if self._shutting_down:
            raise InvalidParamsError("Instance manager is shutting down.")
        if asyncio.current_task() in self._abandoned_launches:
            raise InvalidParamsError("Instance creation was cancelled before launch completed.")
        self._wire_event_listeners(record)
        self._wire_modal_listeners(record.context, record.state)
        self._wire_crash_listeners(record.context, record.browser, record.state)
        self._wire_page_identity(record)
        self._instances[record.name] = record
        mark_operation_started(record.instance_id)
        logger.info("Created instance %r (id=%s)", record.name, record.instance_id)

    def get(self, name: str) -> InstanceRecord:
        """Look up an instance by name.

        Raises InstanceNotFoundError if missing. If the instance's browser
        process has crashed/disconnected, it is evicted from the registry and
        InstanceCrashedError is raised instead of returning a dead record.
        """
        rec = self._instances.get(name)
        if rec is None:
            retiring = self._retired.get(name)
            if retiring is not None and asyncio.current_task() in retiring.operation_tasks:
                return retiring
            raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
        if rec.state.status == "crashed":
            self._evict_crashed(rec)
            raise InstanceCrashedError(
                f"Instance {name!r} crashed (browser process disconnected). It has been "
                f"removed from active instances; check browser_health until cleanup releases its reservation before recreating it."
            )
        return rec

    def _get_raw(self, name: str) -> InstanceRecord | None:
        """Look up an instance by name without the crash check or eviction.

        For internal callers (summaries, reaper) that need to see crashed
        records rather than have them silently evicted.
        """
        return self._instances.get(name)

    def _evict_crashed(self, rec: InstanceRecord) -> None:
        """Schedule exactly one cleanup, without removing a replacement record."""
        if self._instances.get(rec.name) is rec or rec.close_task is not None:
            self._start_close(rec)

    def _track_close(self, task: asyncio.Task[None]) -> None:
        self._closing_tasks.add(task)
        task.add_done_callback(self._close_finished)

    def _close_finished(self, task: asyncio.Task[None]) -> None:
        self._closing_tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _start_close(self, rec: InstanceRecord) -> asyncio.Task[None]:
        if rec.close_task is not None:
            return rec.close_task
        if self._instances.get(rec.name) is rec:
            self._instances.pop(rec.name)
        mark_operation_started(rec.instance_id)
        rec.state.status = "closing"
        self._retired[rec.name] = rec
        task = asyncio.create_task(self._safe_close(rec), name=f"close-{rec.name}")
        rec.close_task = task
        self._track_close(task)
        return task

    async def _close_resources(self, rec: InstanceRecord) -> None:
        try:
            async with rec.lock, rec.modal_lock:
                await rec.stack.aclose()
        except Exception:
            logger.exception("Resource teardown failed for instance %r", rec.name)
            rec.close_error = "Browser resource teardown failed; its name/profile remain reserved."

    async def _safe_close(self, rec: InstanceRecord) -> None:
        """Drain work, cancel blocked operations, and bound resource teardown."""
        duration = self._config.close_timeout_seconds
        deadline = asyncio.get_running_loop().time() + duration
        resources = asyncio.create_task(self._close_resources(rec), name=f"resources-{rec.name}")
        self._track_close(resources)
        done, _ = await asyncio.wait({resources}, timeout=duration / 2)
        if not done:
            for task in tuple(rec.operation_tasks):
                task.cancel()
            remaining = max(0, deadline - asyncio.get_running_loop().time())
            done, _ = await asyncio.wait({resources}, timeout=remaining)
        if not done:
            resources.cancel()
            rec.close_error = f"Browser teardown exceeded {duration:g} seconds; its name/profile remain reserved."
        elif resources.cancelled():
            rec.close_error = "Browser teardown was cancelled; its name/profile remain reserved."
        if rec.close_error is not None:
            rec.state.status = "close_failed"
            logger.warning("Instance %r: %s", rec.name, rec.close_error)
        elif self._retired.get(rec.name) is rec:
            self._retired.pop(rec.name)
            self._reservations.pop(rec.name, None)

    def _validate_record(self, rec: InstanceRecord) -> None:
        if rec.state.status != "live" or self._instances.get(rec.name) is not rec:
            self._evict_crashed(rec)
            raise InstanceCrashedError(
                f"Instance {rec.name!r} is no longer available; its original operation cannot run."
            )

    @property
    def operation_timeout_seconds(self) -> float:
        """Maximum duration of a cooperative operation, including lock waiting."""
        return self._config.operation_timeout_seconds

    @property
    def event_buffer_size(self) -> int:
        """Maximum retained events in each per-instance evidence buffer."""
        return self._config.event_buffer_size

    @property
    def max_result_bytes(self) -> int:
        """Maximum serialized structured result size, including operation metadata."""
        return self._config.max_result_bytes

    def lock_for(self, name: str) -> contextlib.AbstractAsyncContextManager[None]:
        """Return a tracked, bounded context for serialized browser actions."""
        rec = self.get(name)
        return _operation(rec, rec.lock, self._validate_record, self.operation_timeout_seconds)

    def modal_lock_for(self, name: str) -> contextlib.AbstractAsyncContextManager[None]:
        """Serialize modal recovery independently from blocked browser actions."""
        rec = self.get(name)
        return _operation(rec, rec.modal_lock, self._validate_record, self.operation_timeout_seconds)

    def state(self, name: str) -> InstanceState:
        """Return the InstanceState for a named instance."""
        return self.get(name).state

    def list_names(self) -> list[str]:
        """Return the names of all active instances."""
        return list(self._instances.keys())

    async def destroy(self, name: str) -> None:
        """Destroy one instance with bounded graceful drain and cancellation recovery."""
        async with self._registry_lock:
            rec = self._instances.get(name) or self._retired.get(name)
            if rec is None:
                raise InstanceNotFoundError(f"Instance {name!r} does not exist.")
            if asyncio.current_task() in rec.operation_tasks:
                raise InvalidParamsError("An instance cannot be destroyed from its own operation.")
            task = self._start_close(rec)
        await asyncio.shield(task)
        if rec.close_error is not None:
            raise InternalError(rec.close_error)
        logger.info("Destroyed instance %r", name)

    async def list(self) -> list[dict[str, Any]]:
        """Return summary info for all active instances."""
        snapshot = list(self._instances.items())
        return [summarize_instance(rec) for _, rec in snapshot]

    def health_snapshot(self) -> dict[str, Any]:
        """Report server status without launching any browser. Never raises."""
        instances = [summarize_instance(rec) for rec in (*self._instances.values(), *self._retired.values())]
        return {
            "instance_count": len(self._instances),
            "reserved_count": len(self._reservations),
            "max_instances": self._max,
            "instances": instances,
            "failed_launches": list(self._launch_cleanup.values()),
            "config": {
                "idle_ttl_seconds": self._config.idle_ttl_seconds,
                "transport": self._config.transport,
                "host": self._config.host,
                "port": self._config.port,
                "max_instances": self._max,
            },
        }

    def _remember_page(self, rec: InstanceRecord, page: Page) -> str:
        if page not in rec.state.page_ids:
            rec.state.page_ids[page] = str(uuid.uuid4())
        return rec.state.page_ids[page]

    def _wire_page_identity(self, rec: InstanceRecord) -> None:
        def attach(page: Page) -> None:
            self._remember_page(rec, page)
            if rec.state.active_page is None:
                rec.state.active_page = page

            def closed(_page: Page | None = None) -> None:
                rec.state.page_ids.pop(page, None)
                if rec.state.active_page is page:
                    rec.state.active_page = None
                selected = _existing_active_page(rec)
                rec.state.active_page = selected
                rec.state.active_page_index = rec.context.pages.index(selected) if selected is not None else 0

            page.on("close", closed)

        rec.context.on("page", attach)
        for page in rec.context.pages:
            attach(page)

    def page_id(self, name: str, page: Page) -> str:
        """Return a stable identifier for a page owned by this instance."""
        rec = self.get(name)
        if page not in rec.context.pages and page is not rec.state.active_page:
            raise InvalidParamsError("Page is closed or is not owned by this instance.")
        return self._remember_page(rec, page)

    def target_snapshot(self, name: str) -> dict[str, str | None]:
        """Inspect existing target identifiers without creating pages or touching activity."""
        rec = self._instances.get(name)
        if rec is None:
            return {"instance_id": None, "page_id": None}
        page = _existing_active_page(rec)
        return {"instance_id": rec.instance_id, "page_id": rec.state.page_ids.get(page) if page is not None else None}

    async def active_page(self, name: str) -> Page:
        """Return the logical active page by identity, creating one only when empty."""
        rec = self.get(name)
        _touch(rec)
        page = _existing_active_page(rec)
        if page is None:
            page = await rec.context.new_page()
        rec.state.active_page = page
        rec.state.active_page_index = rec.context.pages.index(page) if page in rec.context.pages else 0
        self._remember_page(rec, page)
        mark_operation_started(rec.instance_id, page_id=self.page_id(name, page))
        return page

    def set_active_page(self, name: str, index: int) -> None:
        """Select by the backward-compatible tab index while retaining page identity."""
        rec = self.get(name)
        if index < 0 or index >= len(rec.context.pages):
            raise InvalidParamsError(f"tab index {index} out of range (have {len(rec.context.pages)} pages)")
        rec.state.active_page_index = index
        rec.state.active_page = rec.context.pages[index]
        self._remember_page(rec, rec.state.active_page)

    def get_modal_states(self, name: str) -> list[dict[str, Any]]:
        """Return the list of pending modal states for an instance.

        Entries whose page has closed are pruned automatically.
        """
        states = self.get(name).state.modal_states
        states[:] = [s for s in states if not s["page"].is_closed()]
        return list(states)

    def consume_modal_state(self, name: str, kind: str) -> dict[str, Any] | None:
        """Pop and return the oldest pending modal of the given kind, or None."""
        states = self.get(name).state.modal_states
        for i, state in enumerate(states):
            if state["kind"] == kind:
                return states.pop(i)
        return None

    async def shutdown_all(self) -> None:
        """Stop admission and drain pending launches and teardown without a registry-wide wait."""
        async with self._registry_lock:
            records = (*self._instances.values(), *self._retired.values())
            if any(asyncio.current_task() in rec.operation_tasks for rec in records):
                raise InvalidParamsError("Shutdown cannot run from an instance's own operation.")
            if self._shutdown_task is None:
                self._shutting_down = True
                self._shutdown_task = asyncio.create_task(self._shutdown(), name="instance-shutdown")
            task = self._shutdown_task
        await asyncio.shield(task)

    async def _shutdown(self) -> None:
        pending = set(self._pending_creates.values())
        for task in pending:
            task.cancel()
        closing = {self._start_close(rec) for rec in tuple(self._instances.values())}
        closing.update(rec.close_task for rec in self._retired.values() if rec.close_task is not None)
        closing.update(self._closing_tasks)
        work = pending | closing
        if work:
            _, unfinished = await asyncio.wait(work, timeout=self._config.close_timeout_seconds)
            if unfinished:
                logger.warning("Shutdown deadline reached with %d cleanup tasks still pending", len(unfinished))

    async def reap_once(self, now: datetime | None = None) -> list[str]:
        """Reap idle records using monotonic time, or an explicit wall-clock test instant."""
        ttl = self._config.idle_ttl_seconds
        victims: list[tuple[InstanceRecord, asyncio.Task[None]]] = []
        async with self._registry_lock:
            for rec in tuple(self._instances.values()):
                if rec.lock.locked() or rec.modal_lock.locked() or rec.operation_tasks:
                    continue
                async with rec.lock:
                    idle = (
                        (now - rec.state.last_used_at).total_seconds()
                        if now is not None
                        else monotonic() - rec.state.last_used_monotonic
                    )
                    if rec.state.status == "crashed" or (ttl > 0 and idle > ttl):
                        victims.append((rec, self._start_close(rec)))
        if victims:
            await asyncio.gather(*(asyncio.shield(task) for _, task in victims))
        return [rec.name for rec, _ in victims if rec.close_error is None]

    async def _reaper_loop(self) -> None:
        """Background loop: reap idle/crashed instances every reaper_interval_seconds.

        Wrapped so a single failed iteration never kills the long-lived task.
        """
        interval = self._config.reaper_interval_seconds
        while True:
            await asyncio.sleep(interval)
            try:
                await self.reap_once()
            except Exception:  # never let the reaper loop die; logger.exception exempts BLE001
                logger.exception("Reaper iteration failed")

    def start_reaper(self) -> None:
        """Start the background idle reaper if idle_ttl_seconds enables it."""
        if self._config.idle_ttl_seconds > 0 and self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reaper_loop(), name="idle-reaper")

    async def stop_reaper(self) -> None:
        """Cancel and await the background reaper task, if running."""
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper_task
            self._reaper_task = None

    def _capture_request(self, record: InstanceRecord, page_id: str, req: Request) -> None:
        state = record.state
        entry = {
            "_id": id(req),
            "request_id": str(uuid.uuid4()),
            "page_id": page_id,
            "url": req.url,
            "method": req.method,
            "status": None,
            "resource_type": req.resource_type,
            "failure": None,
        }
        if len(state.network_requests) >= state.network_requests.capacity:
            evicted = state.network_requests[0]
            if state.network_request_index.get(evicted["_id"]) is evicted:
                state.network_request_index.pop(evicted["_id"])
        state.network_request_index[id(req)] = state.network_requests.append(entry)

    def _wire_event_listeners(self, record: InstanceRecord) -> None:
        ctx, state = record.context, record.state

        def _on_response(response: Response) -> None:
            entry = state.network_request_index.get(id(response.request))
            if entry is not None:
                state.network_request_index[id(response.request)] = state.network_requests.update(
                    entry, {"status": response.status}
                )

        def _on_requestfailed(request: Request) -> None:
            entry = state.network_request_index.get(id(request))
            if entry is not None:
                state.network_request_index[id(request)] = state.network_requests.update(
                    entry, {"failure": request.failure or "unknown"}
                )

        def _on_console(page_id: str, message: ConsoleMessage) -> None:
            state.console_messages.append(
                {
                    "type": message.type,
                    "text": message.text,
                    "location": _format_console_location(message.location),
                    "page_id": page_id,
                }
            )

        def _on_pageerror(page_id: str, error: Exception) -> None:
            state.console_messages.append({"type": "error", "text": str(error), "location": None, "page_id": page_id})

        def _attach(page: Page) -> None:
            page_id = self._remember_page(record, page)
            page.on("console", partial(_on_console, page_id))
            page.on("pageerror", partial(_on_pageerror, page_id))
            page.on("request", partial(self._capture_request, record, page_id))
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

    def _wire_crash_listeners(self, ctx: BrowserContext, browser: Browser | None, state: InstanceState) -> None:
        def _mark_crashed(_obj: object = None) -> None:
            if state.status == "live":
                state.status = "crashed"

        ctx.on("close", _mark_crashed)
        if browser is not None:
            browser.on("disconnected", _mark_crashed)


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
