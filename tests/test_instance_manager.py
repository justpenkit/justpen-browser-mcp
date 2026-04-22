"""Unit tests for InstanceManager registry + lifecycle."""

import asyncio
from pathlib import Path

import pytest

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.errors import (
    InstanceAlreadyExistsError,
    InstanceLimitExceededError,
    InstanceNotFoundError,
    ProfileDirInUseError,
)
from justpen_browser_mcp.instance_manager import InstanceManager


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
