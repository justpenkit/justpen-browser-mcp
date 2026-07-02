"""Unit tests for InstanceManager registry + lifecycle."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.errors import (
    InstanceAlreadyExistsError,
    InstanceCrashedError,
    InstanceLimitExceededError,
    InstanceNotFoundError,
    InvalidParamsError,
    ModalStateBlockedError,
    ProfileDirInUseError,
)
from justpen_browser_mcp.instance import InstanceState
from justpen_browser_mcp.instance_manager import InstanceManager, assert_no_modal


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
    assert state.console_messages == []


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
