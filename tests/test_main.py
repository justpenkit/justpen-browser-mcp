"""Verify transport arguments, server failures, and graceful task cleanup."""

from __future__ import annotations

import asyncio
import signal
import subprocess
import sys
from typing import TYPE_CHECKING, Literal
from unittest.mock import AsyncMock, MagicMock

import pytest
from typing_extensions import override

import justpen_browser_mcp.__main__ as main_mod
from justpen_browser_mcp.__main__ import _run_kwargs
from justpen_browser_mcp.config import BrowserServerConfig

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable


@pytest.fixture
async def main_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[dict[signal.Signals, Callable[[], None]], MagicMock]]:
    handlers: dict[signal.Signals, Callable[[], None]] = {}

    def add_handler(sig: signal.Signals, callback: Callable[[], None]) -> None:
        handlers[sig] = callback

    manager = MagicMock(spec=main_mod.InstanceManager)
    manager.stop_reaper = AsyncMock()
    manager.shutdown_all = AsyncMock()
    monkeypatch.setattr(asyncio.get_running_loop(), "add_signal_handler", add_handler)
    monkeypatch.setattr(main_mod, "build_config", lambda _args, _env: BrowserServerConfig())
    monkeypatch.setattr(main_mod, "_ensure_camoufox_binary", AsyncMock())
    monkeypatch.setattr(main_mod, "InstanceManager", lambda _config, **_kwargs: manager)
    monkeypatch.setattr(main_mod, "register_all", MagicMock())
    yield handlers, manager
    # Keep a failing cleanup regression from leaving tasks behind in its test loop.
    pending = [task for task in asyncio.all_tasks() if task.get_name() in {"mcp-server", "stop-signal"}]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


def assert_manager_stopped(manager: MagicMock) -> None:
    manager.start_reaper.assert_called_once_with()
    manager.stop_reaper.assert_awaited_once_with()
    manager.shutdown_all.assert_awaited_once_with()


def test_run_kwargs_stdio_is_empty():
    assert _run_kwargs(BrowserServerConfig(transport="stdio")) == {}


def test_run_kwargs_http_includes_host_port():
    cfg = BrowserServerConfig(transport="http", host="127.0.0.1", port=8931)
    assert _run_kwargs(cfg) == {"transport": "http", "host": "127.0.0.1", "port": 8931}


@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_main_runs_to_completion_when_server_exits(monkeypatch, main_runtime, transport):
    _handlers, manager = main_runtime
    config = BrowserServerConfig(transport=transport, host="127.0.0.1", port=8931)
    monkeypatch.setattr(main_mod, "build_config", lambda _args, _env: config)
    run_async = AsyncMock()
    monkeypatch.setattr(main_mod.mcp, "run_async", run_async)
    before = asyncio.all_tasks()

    await main_mod.main()

    run_async.assert_awaited_once_with(**_run_kwargs(config))
    assert_manager_stopped(manager)
    assert asyncio.all_tasks() == before


@pytest.mark.parametrize("stop_requested", [False, True], ids=["server-failure", "simultaneous-stop-and-failure"])
async def test_main_propagates_server_failure(monkeypatch, main_runtime, *, stop_requested):
    handlers, manager = main_runtime
    before = asyncio.all_tasks()
    failure = RuntimeError("server startup failed")

    async def failing_server() -> None:
        if stop_requested:
            handlers[signal.SIGTERM]()
        raise failure

    monkeypatch.setattr(main_mod.mcp, "run_async", failing_server)
    with pytest.raises(RuntimeError, match="server startup failed") as raised:
        await main_mod.main()
    assert raised.value is failure
    assert_manager_stopped(manager)
    assert asyncio.all_tasks() == before


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
async def test_signal_waits_for_server_cleanup(monkeypatch, main_runtime, sig):
    handlers, manager = main_runtime
    before = asyncio.all_tasks()
    cleaned_up = asyncio.Event()

    async def running_server() -> None:
        try:
            handlers[sig]()
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()

    async def stop_reaper() -> None:
        assert cleaned_up.is_set()

    manager.stop_reaper.side_effect = stop_reaper
    monkeypatch.setattr(main_mod.mcp, "run_async", running_server)
    await asyncio.wait_for(main_mod.main(), timeout=5)
    assert cleaned_up.is_set()
    assert_manager_stopped(manager)
    assert asyncio.all_tasks() == before


async def test_cancelling_main_cleans_up_server(monkeypatch, main_runtime):
    _handlers, manager = main_runtime
    before = asyncio.all_tasks()
    started = asyncio.Event()
    cleaned_up = asyncio.Event()

    async def running_server() -> None:
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()

    monkeypatch.setattr(main_mod.mcp, "run_async", running_server)
    task = asyncio.create_task(main_mod.main())
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned_up.is_set()
    assert_manager_stopped(manager)
    assert asyncio.all_tasks() == before


async def test_cancellation_during_signal_shutdown_propagates(monkeypatch, main_runtime):
    handlers, manager = main_runtime
    before = asyncio.all_tasks()
    cleanup_started = asyncio.Event()

    async def running_server() -> None:
        try:
            handlers[signal.SIGTERM]()
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(main_mod.mcp, "run_async", running_server)
    task = asyncio.create_task(main_mod.main())
    await asyncio.wait_for(cleanup_started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert_manager_stopped(manager)
    assert asyncio.all_tasks() == before


async def test_cancelling_task_drain_still_stops_manager(monkeypatch, main_runtime):
    _handlers, manager = main_runtime
    before = asyncio.all_tasks()
    drain_started = asyncio.Event()
    release_drain = asyncio.Event()

    class DrainingSignal(asyncio.Event):
        @override
        async def wait(self) -> Literal[True]:
            try:
                return await super().wait()
            finally:
                drain_started.set()
                await release_drain.wait()

    monkeypatch.setattr(main_mod.asyncio, "Event", DrainingSignal)
    monkeypatch.setattr(main_mod.mcp, "run_async", AsyncMock())
    task = asyncio.create_task(main_mod.main())
    await asyncio.wait_for(drain_started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert_manager_stopped(manager)
    assert asyncio.all_tasks() == before


@pytest.mark.integration
def test_cli_exits_with_failure_when_server_crashes():
    probe = """
from unittest.mock import AsyncMock
from justpen_browser_mcp import __main__ as entrypoint

async def failing_server():
    raise RuntimeError("server startup failed")

entrypoint._ensure_camoufox_binary = AsyncMock()
entrypoint.mcp.run_async = failing_server
entrypoint.cli()
"""
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False, timeout=30)
    assert result.returncode != 0, result.stderr
    assert "RuntimeError: server startup failed" in result.stderr
    assert "Task exception was never retrieved" not in result.stderr


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
async def test_signal_during_preparation_drains_before_readiness(monkeypatch, main_runtime, sig):
    handlers, manager = main_runtime
    before = asyncio.all_tasks()
    cleaned_up = asyncio.Event()

    async def prepare():
        assert sig in handlers
        try:
            handlers[sig]()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned_up.set()

    run_server = AsyncMock()
    monkeypatch.setattr(main_mod, "_ensure_camoufox_binary", prepare)
    monkeypatch.setattr(main_mod.mcp, "run_async", run_server)
    await main_mod.main()
    assert cleaned_up.is_set()
    run_server.assert_not_awaited()
    manager.start_reaper.assert_not_called()
    assert asyncio.all_tasks() == before


async def test_external_cancellation_during_preparation_propagates(monkeypatch, main_runtime):
    _handlers, manager = main_runtime
    before = asyncio.all_tasks()
    started, cleaned_up = asyncio.Event(), asyncio.Event()

    async def prepare():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()

    monkeypatch.setattr(main_mod, "_ensure_camoufox_binary", prepare)
    task = asyncio.create_task(main_mod.main())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned_up.is_set()
    manager.start_reaper.assert_not_called()
    assert asyncio.all_tasks() == before


async def test_repeated_startup_signals_do_not_interrupt_worker_cleanup(monkeypatch, main_runtime):
    handlers, manager = main_runtime
    cleanup_started, release_cleanup, cleaned_up = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def prepare():
        try:
            handlers[signal.SIGTERM]()
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await release_cleanup.wait()
            cleaned_up.set()

    monkeypatch.setattr(main_mod, "_ensure_camoufox_binary", prepare)
    task = asyncio.create_task(main_mod.main())
    try:
        await asyncio.wait_for(cleanup_started.wait(), timeout=5)
        handlers[signal.SIGTERM]()
        handlers[signal.SIGINT]()
        await asyncio.sleep(0)
        assert not task.done()
        release_cleanup.set()
        await task
        assert cleaned_up.is_set()
        manager.start_reaper.assert_not_called()
    finally:
        release_cleanup.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
