"""Unit tests for InstanceManager registry + lifecycle."""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from justpen_browser_mcp import instance_manager
from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.errors import (
    BrowserMcpError,
    InstanceAlreadyExistsError,
    InstanceCrashedError,
    InstanceLimitExceededError,
    InstanceNotFoundError,
    InvalidParamsError,
    ModalStateBlockedError,
    ProfileDirInUseError,
)
from justpen_browser_mcp.instance import InstanceState, launch_instance
from justpen_browser_mcp.instance_manager import InstanceManager, assert_no_modal
from justpen_browser_mcp.operation_context import Operation, current_operation


@pytest.mark.asyncio
async def test_create_registers_instance(manager):
    rec = await manager.create("alice")
    assert rec.name == "alice"
    assert "alice" in [r["name"] for r in await manager.list()]


@pytest.mark.asyncio
async def test_create_duplicate_raises(manager):
    await manager.create("alice")
    with pytest.raises(InstanceAlreadyExistsError):
        await manager.create("alice")


@pytest.mark.asyncio
async def test_create_limit_exceeded(mock_launch):
    mgr = InstanceManager(BrowserServerConfig(log_level="INFO", max_instances=2))
    await mgr.create("a")
    await mgr.create("b")
    with pytest.raises(InstanceLimitExceededError):
        await mgr.create("c")
    await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_create_profile_dir_collision_raises(manager, tmp_path):
    await manager.create("alice", profile_dir=str(tmp_path))
    with pytest.raises(ProfileDirInUseError, match="alice"):
        await manager.create("bob", profile_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_create_profile_dir_collision_normalizes_path(manager, tmp_path):
    await manager.create("alice", profile_dir=str(tmp_path))
    # Same directory via a path with redundant components
    same_via_parent = str(Path(tmp_path).parent / tmp_path.name)
    with pytest.raises(ProfileDirInUseError):
        await manager.create("bob", profile_dir=same_via_parent)


@pytest.mark.asyncio
async def test_create_ephemeral_no_collision_check(manager):
    # Both profile_dir=None; collision preflight must not fire.
    await manager.create("a")
    await manager.create("b")
    names = {r["name"] for r in await manager.list()}
    assert names == {"a", "b"}


@pytest.mark.asyncio
async def test_destroy_removes_instance(manager):
    await manager.create("alice")
    await manager.destroy("alice")
    assert await manager.list() == []


@pytest.mark.asyncio
async def test_destroy_missing_raises(manager):
    with pytest.raises(InstanceNotFoundError):
        await manager.destroy("nope")


@pytest.mark.asyncio
async def test_destroy_drains_in_flight_op(manager):
    rec = await manager.create("alice")
    hold = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with rec.lock:
            hold.set()
            await release.wait()

    task = asyncio.create_task(holder())
    await hold.wait()
    destroy_task = asyncio.create_task(manager.destroy("alice"))
    await asyncio.sleep(0.05)
    assert not destroy_task.done()
    release.set()
    await task
    await destroy_task
    assert await manager.list() == []


@pytest.mark.asyncio
async def test_list_empty(manager):
    assert await manager.list() == []


@pytest.mark.asyncio
async def test_list_returns_summary_shape(manager, tmp_path):
    await manager.create("alice", profile_dir=str(tmp_path))
    await manager.create("bob")
    summaries = {s["name"]: s for s in await manager.list()}
    assert summaries["alice"]["mode"] == "persistent"
    assert summaries["alice"]["profile_dir"] == str(tmp_path)
    assert summaries["bob"]["mode"] == "ephemeral"
    assert summaries["bob"]["profile_dir"] is None
    for s in summaries.values():
        assert isinstance(s["page_count"], int)
        assert "active_url" in s
        assert "created_at" in s


@pytest.mark.asyncio
async def test_shutdown_all_closes_every_instance(manager):
    await manager.create("a")
    await manager.create("b")
    await manager.create("c")
    await manager.shutdown_all()
    assert await manager.list() == []


@pytest.mark.asyncio
async def test_shutdown_all_continues_on_error(manager, monkeypatch):
    rec_a = await manager.create("a")
    await manager.create("b")
    original_aclose = rec_a.stack.aclose

    async def failing_aclose():
        await original_aclose()
        raise RuntimeError("close boom")

    monkeypatch.setattr(rec_a.stack, "aclose", failing_aclose)
    await manager.shutdown_all()
    # Registry cleared even though one close failed.
    assert await manager.list() == []


@pytest.mark.asyncio
async def test_shutdown_all_acquires_registry_lock(manager):
    """Verify shutdown_all cannot run while registry_lock is held externally."""
    # Simulate create() holding the registry lock during a slow launch.
    held = asyncio.Event()
    release = asyncio.Event()

    async def hold_registry_lock():
        async with manager._registry_lock:
            held.set()
            await release.wait()

    holder = asyncio.create_task(hold_registry_lock())
    await held.wait()

    shutdown_task = asyncio.create_task(manager.shutdown_all())
    for _ in range(10):
        await asyncio.sleep(0)
    assert not shutdown_task.done(), "shutdown_all should block on registry_lock"

    release.set()
    await holder
    await shutdown_task


# --- Additional tests for accessor / helper methods ---


@pytest.mark.asyncio
async def test_get_raises_on_missing(manager):
    with pytest.raises(InstanceNotFoundError):
        manager.get("nope")


@pytest.mark.asyncio
async def test_lock_for_returns_lock(manager):
    await manager.create("alice")
    cm = manager.lock_for("alice")
    async with cm:
        pass


@pytest.mark.asyncio
async def test_lock_for_missing_raises(manager):
    with pytest.raises(InstanceNotFoundError):
        manager.lock_for("nope")


@pytest.mark.asyncio
async def test_state_returns_instance_state(manager):
    await manager.create("alice")
    state = manager.state("alice")
    assert isinstance(state, InstanceState)
    assert not state.console_messages


@pytest.mark.asyncio
async def test_state_missing_raises(manager):
    with pytest.raises(InstanceNotFoundError):
        manager.state("nope")


@pytest.mark.asyncio
async def test_list_names_snapshot(manager):
    await manager.create("a")
    await manager.create("b")
    names = manager.list_names()
    assert set(names) == {"a", "b"}


@pytest.mark.asyncio
async def test_active_page_creates_when_no_pages(manager):
    rec = await manager.create("alice")
    new_page = MagicMock()
    rec.context.new_page = AsyncMock(return_value=new_page)
    rec.context.pages = []
    page = await manager.active_page("alice")
    assert page is new_page
    assert rec.state.active_page_index == 0


@pytest.mark.asyncio
async def test_active_page_returns_existing(manager):
    rec = await manager.create("alice")
    p0 = MagicMock()
    p1 = MagicMock()
    rec.context.pages = [p0, p1]
    rec.state.active_page_index = 1
    page = await manager.active_page("alice")
    assert page is p1


@pytest.mark.asyncio
async def test_active_page_clamps_out_of_range(manager):
    rec = await manager.create("alice")
    p0 = MagicMock()
    rec.context.pages = [p0]
    rec.state.active_page_index = 99
    page = await manager.active_page("alice")
    assert page is p0
    assert rec.state.active_page_index == 0


@pytest.mark.asyncio
async def test_set_active_page_valid(manager):
    rec = await manager.create("alice")
    rec.context.pages = [MagicMock(), MagicMock()]
    manager.set_active_page("alice", 1)
    assert rec.state.active_page_index == 1


@pytest.mark.asyncio
async def test_set_active_page_missing_instance_raises(manager):
    with pytest.raises(InstanceNotFoundError):
        manager.set_active_page("nope", 0)


@pytest.mark.asyncio
async def test_set_active_page_out_of_range_raises(manager):
    rec = await manager.create("alice")
    rec.context.pages = [MagicMock()]
    with pytest.raises(InvalidParamsError):
        manager.set_active_page("alice", 5)


@pytest.mark.asyncio
async def test_get_modal_states_empty(manager):
    await manager.create("alice")
    assert manager.get_modal_states("alice") == []


@pytest.mark.asyncio
async def test_get_modal_states_prunes_closed_pages(manager):
    rec = await manager.create("alice")
    open_page = MagicMock()
    open_page.is_closed.return_value = False
    closed_page = MagicMock()
    closed_page.is_closed.return_value = True
    rec.state.modal_states.append({"kind": "dialog", "object": MagicMock(), "page": closed_page})
    rec.state.modal_states.append({"kind": "dialog", "object": MagicMock(), "page": open_page})
    states = manager.get_modal_states("alice")
    assert len(states) == 1
    assert states[0]["page"] is open_page


@pytest.mark.asyncio
async def test_get_modal_states_missing_raises(manager):
    with pytest.raises(InstanceNotFoundError):
        manager.get_modal_states("nope")


@pytest.mark.asyncio
async def test_consume_modal_state_pops_oldest_of_kind(manager):
    rec = await manager.create("alice")
    dialog_obj = MagicMock()
    filechooser_obj = MagicMock()
    page = MagicMock()
    rec.state.modal_states.extend(
        [
            {"kind": "dialog", "object": dialog_obj, "page": page},
            {"kind": "filechooser", "object": filechooser_obj, "page": page},
        ]
    )
    popped = manager.consume_modal_state("alice", "dialog")
    assert popped is not None
    assert popped["object"] is dialog_obj
    # filechooser remains
    assert len(rec.state.modal_states) == 1
    assert rec.state.modal_states[0]["kind"] == "filechooser"


@pytest.mark.asyncio
async def test_consume_modal_state_none_when_missing_kind(manager):
    await manager.create("alice")
    assert manager.consume_modal_state("alice", "dialog") is None


@pytest.mark.asyncio
async def test_consume_modal_state_missing_instance_raises(manager):
    with pytest.raises(InstanceNotFoundError):
        manager.consume_modal_state("nope", "dialog")


@pytest.mark.asyncio
async def test_assert_no_modal_noop_when_empty(manager):
    await manager.create("alice")
    # Should not raise
    assert_no_modal(manager, "alice")


@pytest.mark.asyncio
async def test_assert_no_modal_raises_on_dialog(manager):
    rec = await manager.create("alice")
    dialog = MagicMock()
    dialog.type = "confirm"
    dialog.message = "Leave page?"
    page = MagicMock()
    page.is_closed.return_value = False
    rec.state.modal_states.append({"kind": "dialog", "object": dialog, "page": page})
    with pytest.raises(ModalStateBlockedError, match="dialog"):
        assert_no_modal(manager, "alice")


@pytest.mark.asyncio
async def test_assert_no_modal_raises_on_filechooser(manager):
    rec = await manager.create("alice")
    fc = MagicMock()
    page = MagicMock()
    page.is_closed.return_value = False
    rec.state.modal_states.append({"kind": "filechooser", "object": fc, "page": page})
    with pytest.raises(ModalStateBlockedError, match="file-chooser"):
        assert_no_modal(manager, "alice")


@pytest.mark.asyncio
async def test_create_applies_server_defaults(mock_launch):
    cfg = BrowserServerConfig(
        max_instances=5,
        proxy={"server": "http://p:8080"},
        camoufox_os=("windows",),
        locale="en-US",
        block_images=True,
    )
    mgr = InstanceManager(cfg)
    try:
        await mgr.create("a")
        kwargs = mock_launch[0]["kwargs"]
        assert kwargs["proxy"] == {"server": "http://p:8080"}
        assert kwargs["camoufox_os"] == ("windows",)
        assert kwargs["locale"] == "en-US"
        assert kwargs["block_images"] is True
    finally:
        await mgr.shutdown_all()


@pytest.mark.asyncio
async def test_create_param_overrides_server_default(mock_launch):
    cfg = BrowserServerConfig(max_instances=5, proxy={"server": "http://default:8080"})
    mgr = InstanceManager(cfg)
    try:
        await mgr.create("a", proxy={"server": "http://override:9090"})
        assert mock_launch[0]["kwargs"]["proxy"] == {"server": "http://override:9090"}
    finally:
        await mgr.shutdown_all()


# --- Crash detection / lazy eviction / touch-on-lock ---


@pytest.mark.asyncio
async def test_get_raises_and_evicts_crashed_instance(manager):
    rec = await manager.create("a")
    rec.state.status = "crashed"
    with pytest.raises(InstanceCrashedError):
        manager.get("a")
    # evicted → now not found
    with pytest.raises(InstanceNotFoundError):
        manager.get("a")


@pytest.mark.asyncio
async def test_lock_for_stamps_last_used(manager):
    rec = await manager.create("a")
    old = rec.state.last_used_at
    async with manager.lock_for("a"):
        pass
    assert rec.state.last_used_at >= old


@pytest.mark.asyncio
async def test_disconnect_marks_crashed(manager, mock_launch):
    # mock_launch ctx.on records handlers; simulate the disconnected callback
    await manager.create("a")
    ctx = mock_launch[0]["ctx"]
    # find the "close" handler registered on ctx and invoke it
    close_cbs = [c.args[1] for c in ctx.on.call_args_list if c.args[0] == "close"]
    assert close_cbs
    close_cbs[0]()
    rec = manager._get_raw("a")
    assert rec is not None
    assert rec.state.status == "crashed"


@pytest.mark.asyncio
async def test_browser_disconnected_marks_crashed(manager):
    """I2: the ephemeral browser.on('disconnected', ...) path must also mark crashed.

    mock_launch always returns browser=None, so this path is never exercised via
    create(); wire the listeners directly with a MagicMock browser to cover it.
    """
    ctx = MagicMock()
    ctx.pages = []
    ctx.on = MagicMock()
    browser = MagicMock()
    browser.on = MagicMock()
    state = InstanceState()

    manager._wire_crash_listeners(ctx, browser, state)

    disconnected_cbs = [c.args[1] for c in browser.on.call_args_list if c.args[0] == "disconnected"]
    assert disconnected_cbs
    disconnected_cbs[0]()
    assert state.status == "crashed"


@pytest.mark.asyncio
async def test_get_evicted_crashed_instance_closes_stack(manager):
    """C1: get()'s crash-eviction must schedule teardown of the record's stack."""
    rec = await manager.create("a")
    rec.stack.aclose = AsyncMock()
    rec.state.status = "crashed"
    with pytest.raises(InstanceCrashedError):
        manager.get("a")
    assert manager._closing_tasks
    await asyncio.sleep(0)
    await asyncio.gather(*list(manager._closing_tasks), return_exceptions=True)
    rec.stack.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_destroy_crashed_instance_succeeds(manager):
    """C2: destroy() must tear down a crashed instance instead of raising."""
    rec = await manager.create("a")
    rec.stack.aclose = AsyncMock()
    rec.state.status = "crashed"
    await manager.destroy("a")
    assert await manager.list() == []
    rec.stack.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_destroy_missing_still_raises(manager):
    with pytest.raises(InstanceNotFoundError):
        await manager.destroy("nope")


@pytest.mark.asyncio
async def test_lock_for_toctou_crash_raises_and_evicts(manager):
    """I1: if status flips to crashed while a caller awaits the instance lock,
    the waiter must raise InstanceCrashedError (not proceed on a dead record),
    and the record must be evicted from the registry.
    """
    rec = await manager.create("a")
    rec.stack.aclose = AsyncMock()

    # Hold the lock so lock_for("a") blocks on acquire.
    await rec.lock.acquire()

    waiter_started = asyncio.Event()

    async def waiter():
        waiter_started.set()
        async with manager.lock_for("a"):
            pass  # pragma: no cover - should never get here

    task = asyncio.create_task(waiter())
    await waiter_started.wait()
    # Let the waiter actually block on rec.lock.acquire().
    for _ in range(5):
        await asyncio.sleep(0)

    # Simulate a crash callback firing while the waiter is queued for the lock.
    rec.state.status = "crashed"
    rec.lock.release()

    with pytest.raises(InstanceCrashedError):
        await task

    # Evicted from the registry.
    with pytest.raises(InstanceNotFoundError):
        manager.get("a")

    # Teardown of the evicted record was scheduled.
    await asyncio.sleep(0)
    await asyncio.gather(*list(manager._closing_tasks), return_exceptions=True)
    rec.stack.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_reap_once_evicts_idle(manager):
    manager._config = manager._config.__class__(**{**manager._config.__dict__, "idle_ttl_seconds": 100})
    rec = await manager.create("a")
    rec.state.last_used_at = datetime.now(tz=UTC) - timedelta(seconds=200)
    evicted = await manager.reap_once(datetime.now(tz=UTC))
    assert "a" in evicted

    with pytest.raises(InstanceNotFoundError):
        manager.get("a")


@pytest.mark.asyncio
async def test_reap_once_keeps_fresh(manager):
    manager._config = manager._config.__class__(**{**manager._config.__dict__, "idle_ttl_seconds": 100})
    await manager.create("a")
    evicted = await manager.reap_once(datetime.now(tz=UTC))
    assert evicted == []


@pytest.mark.asyncio
async def test_reap_once_noop_when_ttl_zero(manager):
    rec = await manager.create("a")
    rec.state.last_used_at = datetime.now(tz=UTC) - timedelta(days=1)
    evicted = await manager.reap_once(datetime.now(tz=UTC))
    assert evicted == []  # ttl=0 disables reaping


@pytest.mark.asyncio
async def test_reap_once_evicts_crashed_regardless_of_ttl(manager):
    """Crashed instances are a reaper backstop even when idle_ttl_seconds is disabled."""
    rec = await manager.create("a")
    rec.stack.aclose = AsyncMock()
    rec.state.status = "crashed"
    evicted = await manager.reap_once(datetime.now(tz=UTC))
    assert "a" in evicted
    with pytest.raises(InstanceNotFoundError):
        manager.get("a")
    rec.stack.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_reap_once_tolerates_concurrent_eviction_mid_pass(manager):
    """Concurrent crash eviction and reaping share one resource owner per record."""
    rec_a = await manager.create("a")
    rec_b = await manager.create("b")
    rec_a.state.status = "crashed"
    rec_b.state.status = "crashed"

    async def _evict_b_concurrently() -> None:
        manager._evict_crashed(rec_b)

    rec_a.stack.aclose = AsyncMock(side_effect=_evict_b_concurrently)
    rec_b.stack.aclose = AsyncMock()

    evicted = await manager.reap_once(datetime.now(tz=UTC))

    assert evicted == ["a", "b"]  # victim list is built up front, before either close runs
    assert manager._instances == {}
    rec_a.stack.aclose.assert_awaited_once()
    rec_b.stack.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_reaper_noop_when_ttl_zero(manager):
    """idle_ttl_seconds == 0 (the default) must not spawn a background task."""
    assert manager._config.idle_ttl_seconds == 0
    manager.start_reaper()
    assert manager._reaper_task is None
    # Safe no-op: stopping a reaper that never started must not raise.
    await manager.stop_reaper()


@pytest.mark.asyncio
async def test_start_reaper_starts_task_and_is_idempotent(manager):
    manager._config = manager._config.__class__(
        **{**manager._config.__dict__, "idle_ttl_seconds": 60, "reaper_interval_seconds": 1}
    )
    manager.start_reaper()
    assert manager._reaper_task is not None
    task = manager._reaper_task

    # Calling start_reaper again must not spawn a second task.
    manager.start_reaper()
    assert manager._reaper_task is task

    await manager.stop_reaper()
    assert manager._reaper_task is None
    assert task.cancelled() or task.done()


async def test_old_crashed_handle_cannot_evict_replacement(manager):
    old = await manager.create("same")
    old.stack.aclose = AsyncMock()
    stale_lock = manager.lock_for("same")
    old.state.status = "crashed"
    with pytest.raises(InstanceCrashedError):
        manager.get("same")
    await asyncio.gather(*manager._closing_tasks)
    replacement = await manager.create("same")
    with pytest.raises(InstanceCrashedError):
        async with stale_lock:
            pytest.fail("stale record must not run")
    assert manager.get("same") is replacement
    await asyncio.gather(*manager._closing_tasks)
    old.stack.aclose.assert_awaited_once()


async def test_crash_cleanup_has_one_owner(manager):
    record = await manager.create("same")
    record.stack.aclose = AsyncMock()
    record.state.status = "crashed"
    manager._evict_crashed(record)
    manager._evict_crashed(record)
    await manager.shutdown_all()
    record.stack.aclose.assert_awaited_once()


async def test_closing_name_and_profile_stay_reserved_without_blocking_others(manager, tmp_path):
    record = await manager.create("closing", profile_dir=str(tmp_path))
    entered = asyncio.Event()
    release = asyncio.Event()

    async def close():
        entered.set()
        await release.wait()

    record.stack.aclose = AsyncMock(side_effect=close)
    destroy = asyncio.create_task(manager.destroy("closing"))
    try:
        await entered.wait()
        async with asyncio.timeout(0.5):
            with pytest.raises(InstanceAlreadyExistsError):
                await manager.create("closing")
            with pytest.raises(ProfileDirInUseError):
                await manager.create("other-profile-user", profile_dir=str(tmp_path))
            await manager.create("healthy")
            await manager.destroy("healthy")
    finally:
        release.set()
        await destroy
    await manager.create("replacement", profile_dir=str(tmp_path))


async def test_slow_launch_reserves_capacity_without_serializing_other_records(manager, monkeypatch):
    launch = instance_manager.launch_instance
    entered = asyncio.Event()
    release = asyncio.Event()

    async def delayed_launch(**kwargs):
        if kwargs.get("locale") == "slow":
            entered.set()
            await release.wait()
        return await launch(**kwargs)

    monkeypatch.setattr(instance_manager, "launch_instance", delayed_launch)
    pending = asyncio.create_task(manager.create("slow", locale="slow"))
    try:
        await entered.wait()
        async with asyncio.timeout(0.5):
            with pytest.raises(InstanceAlreadyExistsError):
                await manager.create("slow")
            await manager.create("healthy")
            await manager.destroy("healthy")
    finally:
        release.set()
        await pending


async def test_destroy_busy_record_does_not_hold_registry_lock(manager):
    record = await manager.create("busy")
    await manager.create("healthy")
    await record.lock.acquire()
    destroy = asyncio.create_task(manager.destroy("busy"))
    try:
        await asyncio.sleep(0)
        async with asyncio.timeout(0.5):
            await manager.destroy("healthy")
    finally:
        record.lock.release()
        await destroy


async def test_reaper_skips_busy_record_and_counts_operation_completion(manager):
    manager._config = BrowserServerConfig(idle_ttl_seconds=100)
    record = await manager.create("busy")
    record.state.last_used_at = datetime.now(UTC) - timedelta(seconds=200)
    async with manager.lock_for("busy"):
        record.state.last_used_at = datetime.now(UTC) - timedelta(seconds=200)
        async with asyncio.timeout(0.5):
            assert await manager.reap_once(datetime.now(UTC)) == []
        before_completion = datetime.now(UTC)
    assert record.state.last_used_at >= before_completion
    assert await manager.reap_once(datetime.now(UTC)) == []


async def test_active_page_identity_survives_earlier_tab_closing(manager):
    record = await manager.create("tabs")
    pages = [MagicMock(), MagicMock(), MagicMock()]
    record.context.pages = pages[:]
    manager.set_active_page("tabs", 1)
    before = await manager.active_page("tabs")
    record.context.pages.pop(0)
    assert await manager.active_page("tabs") is before
    assert record.state.active_page_index == 0


async def test_target_snapshot_does_not_create_page_and_has_stable_ids(manager):
    record = await manager.create("tabs")
    empty = manager.target_snapshot("tabs")
    assert empty["instance_id"]
    assert empty["page_id"] is None
    record.context.new_page.assert_not_awaited()
    page = MagicMock()
    record.context.pages = [page]
    manager.set_active_page("tabs", 0)
    first = manager.target_snapshot("tabs")
    assert first["page_id"] == manager.page_id("tabs", page)
    assert manager.target_snapshot("tabs") == first
    await manager.destroy("tabs")
    replacement = await manager.create("tabs")
    assert replacement.instance_id != record.instance_id
    assert manager.target_snapshot("missing") == {"instance_id": None, "page_id": None}


async def test_modal_recovery_does_not_wait_for_action_lock(manager):
    await manager.create("modal")
    async with manager.lock_for("modal"):
        async with asyncio.timeout(0.5):
            async with manager.modal_lock_for("modal"):
                pass


async def test_operation_deadline_releases_lock(mock_launch):
    manager = InstanceManager(BrowserServerConfig(operation_timeout_seconds=0.03))
    record = await manager.create("slow")
    try:
        with pytest.raises(BrowserMcpError) as error:
            async with manager.lock_for("slow"):
                await asyncio.Event().wait()
        assert error.value.error_type == "operation_timeout"
        assert not record.lock.locked()
        async with manager.lock_for("slow"):
            pass
    finally:
        await manager.shutdown_all()


async def test_destroy_cancels_blocked_operation_after_grace(mock_launch):
    manager = InstanceManager(BrowserServerConfig(close_timeout_seconds=0.1))
    record = await manager.create("slow")
    entered = asyncio.Event()
    drained = asyncio.Event()

    async def operation():
        async with manager.lock_for("slow"):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                drained.set()

    record.stack.aclose = AsyncMock(side_effect=lambda: drained.is_set() or pytest.fail("closed before drain"))
    task = asyncio.create_task(operation())
    await entered.wait()
    async with asyncio.timeout(0.5):
        await manager.destroy("slow")
    assert task.cancelled()
    assert drained.is_set()
    record.stack.aclose.assert_awaited_once()
    await manager.shutdown_all()


async def test_self_destroy_rejected_without_deadlock(manager):
    await manager.create("self")
    async with manager.lock_for("self"):
        async with asyncio.timeout(0.5):
            with pytest.raises(InvalidParamsError, match="own operation"):
                await manager.destroy("self")
    assert manager.get("self")


async def test_close_deadline_keeps_failed_profile_reserved(mock_launch, tmp_path):
    manager = InstanceManager(BrowserServerConfig(close_timeout_seconds=0.03))
    record = await manager.create("slow", profile_dir=str(tmp_path))
    record.stack.aclose = AsyncMock(side_effect=asyncio.Event().wait)
    async with asyncio.timeout(0.5):
        with pytest.raises(BrowserMcpError):
            await manager.destroy("slow")
    with pytest.raises(ProfileDirInUseError):
        await manager.create("other", profile_dir=str(tmp_path))
    await manager.shutdown_all()


async def test_shutdown_cancels_pending_launch_and_rejects_new_creates(manager, monkeypatch):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def pending_launch(**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(instance_manager, "launch_instance", pending_launch)
    task = asyncio.create_task(manager.create("pending"))
    await entered.wait()
    try:
        async with asyncio.timeout(0.5):
            await manager.shutdown_all()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert cancelled.is_set()
    assert not manager.list_names()
    with pytest.raises(InvalidParamsError, match="shutting down"):
        await manager.create("late")


async def test_pending_create_counts_toward_capacity(mock_launch, monkeypatch):
    manager = InstanceManager(BrowserServerConfig(max_instances=1))
    launch = instance_manager.launch_instance
    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_launch(**kwargs):
        entered.set()
        await release.wait()
        return await launch(**kwargs)

    monkeypatch.setattr(instance_manager, "launch_instance", slow_launch)
    task = asyncio.create_task(manager.create("pending"))
    try:
        await entered.wait()
        async with asyncio.timeout(0.5):
            with pytest.raises(InstanceLimitExceededError):
                await manager.create("other")
    finally:
        release.set()
        await task
        await manager.shutdown_all()


async def test_cancelled_launch_before_start_releases_reservation(manager):
    creation = asyncio.create_task(manager.create("pending"))
    await asyncio.sleep(0)
    pending = manager._pending_creates["pending"]
    pending.cancel()
    await asyncio.gather(creation, return_exceptions=True)
    assert "pending" not in manager._pending_creates
    await manager.create("pending")


async def test_cancelled_destroy_still_finishes_owned_cleanup(manager):
    record = await manager.create("closing")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def close():
        entered.set()
        await release.wait()

    record.stack.aclose = AsyncMock(side_effect=close)
    task = asyncio.create_task(manager.destroy("closing"))
    await entered.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    with pytest.raises(InstanceAlreadyExistsError):
        await manager.create("closing")
    release.set()
    await asyncio.gather(*manager._closing_tasks)
    await manager.create("closing")
    record.stack.aclose.assert_awaited_once()


async def test_page_identity_mapping_discards_closed_pages(manager):
    record = await manager.create("tabs")
    page = MagicMock()
    page.is_closed.return_value = False
    record.context.pages = [page]
    for call in record.context.on.call_args_list:
        if call.args[0] == "page":
            call.args[1](page)
    assert manager.page_id("tabs", page)
    record.context.pages = []
    for call in page.on.call_args_list:
        if call.args[0] == "close":
            call.args[1]()
    assert page not in record.state.page_ids
    assert record.state.active_page is None
    with pytest.raises(InvalidParamsError):
        manager.page_id("tabs", page)
    assert page not in record.state.page_ids


async def test_reaper_production_clock_ignores_wall_clock_adjustment(manager, monkeypatch):
    manager._config = BrowserServerConfig(idle_ttl_seconds=100)
    record = await manager.create("idle")
    record.state.last_used_monotonic = 10
    record.state.last_used_at = datetime.now(UTC) + timedelta(days=1)
    monkeypatch.setattr("justpen_browser_mcp.instance_manager.monotonic", lambda: 200)
    assert await manager.reap_once() == ["idle"]


async def test_operation_timeout_includes_waiting_without_unlocking_other_owner(mock_launch):
    manager = InstanceManager(BrowserServerConfig(operation_timeout_seconds=0.03))
    record = await manager.create("busy")
    await record.lock.acquire()
    try:
        with pytest.raises(BrowserMcpError) as error:
            async with manager.lock_for("busy"):
                pytest.fail("lock is held elsewhere")
        assert error.value.error_type == "operation_timeout"
        assert record.lock.locked()
        assert not record.operation_tasks
    finally:
        record.lock.release()
        await manager.shutdown_all()


async def test_self_shutdown_rejected_without_deadlock(manager):
    await manager.create("self")
    async with manager.lock_for("self"):
        with pytest.raises(InvalidParamsError, match="own operation"):
            await manager.shutdown_all()
    assert manager.get("self")


async def test_manager_records_execution_start_only_after_lock_acquisition(manager):
    record = await manager.create("target")
    operation = Operation(tool="browser_probe")
    token = current_operation.set(operation)
    try:
        context = manager.lock_for("target")
        assert not operation.execution_started
        async with context:
            assert operation.execution_started
            assert operation.instance_id == record.instance_id
    finally:
        current_operation.reset(token)


async def test_cancelled_create_does_not_publish_late_launch(manager, monkeypatch):
    launch = instance_manager.launch_instance
    entered = asyncio.Event()
    release = asyncio.Event()

    async def launch_finishing_after_cancellation(**kwargs):
        entered.set()
        with contextlib.suppress(asyncio.CancelledError):
            await release.wait()
        return await launch(**kwargs)

    monkeypatch.setattr(instance_manager, "launch_instance", launch_finishing_after_cancellation)
    creation = asyncio.create_task(manager.create("late"))
    await entered.wait()
    creation.cancel()
    await asyncio.gather(creation, return_exceptions=True)
    assert "late" not in manager.list_names()
    assert "late" not in manager._reservations


async def test_partial_initialization_keeps_profile_reserved_until_cleanup_finishes(manager, monkeypatch, tmp_path):
    launch = instance_manager.launch_instance
    entered = asyncio.Event()
    release = asyncio.Event()
    close = AsyncMock()

    async def blocking_close():
        entered.set()
        await release.wait()

    close.side_effect = blocking_close

    async def allocated_launch(**kwargs):
        stack, context, browser = await launch(**kwargs)
        stack.aclose = close
        return stack, context, browser

    def broken_initializer(record):
        raise RuntimeError("initialization failed")

    monkeypatch.setattr(instance_manager, "launch_instance", allocated_launch)
    monkeypatch.setattr(manager, "_wire_page_identity", broken_initializer)
    creation = asyncio.create_task(manager.create("initializing", profile_dir=str(tmp_path)))
    try:
        await entered.wait()
        with pytest.raises(ProfileDirInUseError):
            await manager.create("other", profile_dir=str(tmp_path))
    finally:
        release.set()
        with pytest.raises(RuntimeError, match="initialization failed"):
            await creation
    close.assert_awaited_once()
    assert "initializing" not in manager._reservations


@pytest.mark.parametrize("failure", ["exception", "cancelled", "timeout"])
async def test_failed_launch_rollback_keeps_native_allocation_reserved(monkeypatch, failure):
    browser = MagicMock()
    browser.new_context = AsyncMock(side_effect=RuntimeError("new context failed"))
    camoufox = MagicMock()
    camoufox.__aenter__ = AsyncMock(return_value=browser)
    error = RuntimeError("close failed") if failure == "exception" else asyncio.CancelledError()
    camoufox.__aexit__ = AsyncMock(side_effect=error)
    if failure == "timeout":

        async def stall(*args):
            await asyncio.Event().wait()

        camoufox.__aexit__.side_effect = stall
    monkeypatch.setattr("justpen_browser_mcp.instance.AsyncCamoufox", MagicMock(return_value=camoufox))
    monkeypatch.setattr(instance_manager, "launch_instance", launch_instance)
    manager = InstanceManager(BrowserServerConfig(max_instances=1, close_timeout_seconds=0.03))
    try:
        with pytest.raises(RuntimeError, match="new context failed"):
            await manager.create("partial")
        with pytest.raises(InstanceAlreadyExistsError):
            await manager.create("partial")
        with pytest.raises(InstanceLimitExceededError):
            await manager.create("other")
        health = manager.health_snapshot()
        assert health["reserved_count"] == 1
        assert health["failed_launches"][0]["status"] == "close_failed"
        camoufox.__aexit__.assert_awaited_once()
    finally:
        await manager.shutdown_all()


async def test_cancelled_teardown_is_failure_and_retains_reservation(manager):
    record = await manager.create("cancelled-close")
    record.stack.aclose = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(BrowserMcpError):
        await manager.destroy(record.name)
    assert record.state.status == "close_failed"
    with pytest.raises(InstanceAlreadyExistsError):
        await manager.create(record.name)


async def test_late_disconnect_preserves_failed_close_status(manager):
    record = await manager.create("failed-close")
    record.stack.aclose = AsyncMock(side_effect=RuntimeError("close failed"))
    with pytest.raises(BrowserMcpError):
        await manager.destroy(record.name)
    for event in record.context.on.call_args_list:
        if event.args[0] == "close":
            event.args[1]()
    assert record.state.status == "close_failed"


async def test_self_shutdown_rejected_while_concurrent_destroy_is_draining(manager):
    await manager.create("self")
    destroy = None
    try:
        async with manager.lock_for("self"):
            destroy = asyncio.create_task(manager.destroy("self"))
            await asyncio.sleep(0)
            assert "self" not in manager.list_names()
            async with asyncio.timeout(0.1):
                with pytest.raises(InvalidParamsError, match="own operation"):
                    await manager.shutdown_all()
    finally:
        if destroy is not None:
            await destroy
