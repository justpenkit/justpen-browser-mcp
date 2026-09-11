"""Pin browser installation and reject successful-but-ineffective SDK fetches."""

import asyncio
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, call

import pytest

import justpen_browser_mcp.__main__ as entrypoint
import justpen_browser_mcp.browser_runtime as runtime
from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.errors import BinaryNotFoundError


@pytest.fixture
def browser_fetch(monkeypatch):
    process = MagicMock(returncode=0)
    process.communicate = AsyncMock(return_value=(b"", b""))
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(runtime.asyncio, "create_subprocess_exec", launch)
    return launch, process


async def test_correct_browser_does_not_fetch(monkeypatch, browser_fetch):
    launch, _process = browser_fetch
    monkeypatch.setattr(runtime, "installed_verstr", lambda: "135.0.1-beta.24")

    await runtime.ensure_camoufox_binary()

    launch.assert_not_awaited()


@pytest.mark.parametrize("current", ["152.0.4-beta.30", "135.0.1-beta.23"])
async def test_wrong_browser_fetches_exact_release(monkeypatch, browser_fetch, current):
    launch, _process = browser_fetch
    monkeypatch.setattr(runtime, "installed_verstr", MagicMock(side_effect=[current, "135.0.1-beta.24"]))

    await runtime.ensure_camoufox_binary()

    launch.assert_has_awaits(
        [
            call(
                sys.executable,
                "-m",
                "camoufox",
                "fetch",
                "official/135.0.1-beta.24",
                stdout=sys.stderr,
                stderr=asyncio.subprocess.PIPE,
            ),
            call(
                sys.executable,
                "-m",
                "camoufox",
                "set",
                "official/stable/135.0.1-beta.24",
                stdout=sys.stderr,
                stderr=asyncio.subprocess.PIPE,
            ),
        ]
    )
    assert launch.await_count == 2


@pytest.mark.parametrize("failure", [OSError("missing"), RuntimeError("missing"), ValueError("invalid version")])
async def test_missing_browser_fetches_exact_release(monkeypatch, browser_fetch, failure):
    launch, _process = browser_fetch
    monkeypatch.setattr(runtime, "installed_verstr", MagicMock(side_effect=[failure, "135.0.1-beta.24"]))

    await runtime.ensure_camoufox_binary()

    assert launch.await_args_list[0].args[-1] == "official/135.0.1-beta.24"


async def test_failed_fetch_reports_stderr(monkeypatch, browser_fetch):
    _launch, process = browser_fetch
    process.returncode = 2
    process.communicate.return_value = (b"", b"download unavailable")
    monkeypatch.setattr(runtime, "installed_verstr", MagicMock(side_effect=RuntimeError("missing")))

    with pytest.raises(BinaryNotFoundError, match="download unavailable"):
        await runtime.ensure_camoufox_binary()


async def test_zero_exit_does_not_accept_wrong_version(monkeypatch, browser_fetch):
    monkeypatch.setattr(runtime, "installed_verstr", lambda: "152.0.4-beta.30")

    with pytest.raises(BinaryNotFoundError, match=r"135\.0\.1-beta\.24"):
        await runtime.ensure_camoufox_binary()


async def test_zero_exit_does_not_accept_missing_install(monkeypatch, browser_fetch):
    monkeypatch.setattr(runtime, "installed_verstr", MagicMock(side_effect=RuntimeError("still missing")))

    with pytest.raises(BinaryNotFoundError, match=r"135\.0\.1-beta\.24"):
        await runtime.ensure_camoufox_binary()


async def test_cached_browser_is_selected_after_fetch(monkeypatch, browser_fetch):
    launch, _process = browser_fetch
    monkeypatch.setattr(runtime, "installed_verstr", MagicMock(side_effect=["152.0.4-beta.30", "135.0.1-beta.24"]))

    await runtime.ensure_camoufox_binary()

    assert [call.args[3:] for call in launch.await_args_list] == [
        ("fetch", "official/135.0.1-beta.24"),
        ("set", "official/stable/135.0.1-beta.24"),
    ]


async def test_browser_failure_prevents_mcp_start(monkeypatch):
    failure = BinaryNotFoundError("pinned browser unavailable")
    monkeypatch.setattr(entrypoint, "build_config", lambda _args, _env: BrowserServerConfig())
    monkeypatch.setattr(entrypoint, "_ensure_camoufox_binary", AsyncMock(side_effect=failure))
    run_server = AsyncMock()
    monkeypatch.setattr(entrypoint.mcp, "run_async", run_server)

    with pytest.raises(BinaryNotFoundError, match="pinned browser unavailable"):
        await entrypoint.main()

    run_server.assert_not_awaited()


def test_browser_helper_cli_exits_nonzero_on_failure():
    probe = """
from unittest.mock import AsyncMock
from justpen_browser_mcp import browser_runtime
from justpen_browser_mcp.errors import BinaryNotFoundError

browser_runtime.ensure_camoufox_binary = AsyncMock(side_effect=BinaryNotFoundError("browser unavailable"))
browser_runtime.cli()
"""
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False, timeout=30)
    assert result.returncode != 0
    assert "BinaryNotFoundError: browser unavailable" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("termination_times_out", [False, True])
async def test_cancelled_fetch_stops_and_reaps_its_child(monkeypatch, browser_fetch, termination_times_out):
    launch, process = browser_fetch
    process.returncode = None
    started = asyncio.Event()

    async def communicate():
        started.set()
        await asyncio.Event().wait()

    process.communicate.side_effect = communicate
    process.wait = AsyncMock(side_effect=[TimeoutError(), -9] if termination_times_out else [-15])
    monkeypatch.setattr(runtime, "installed_verstr", lambda: "152.0.4-beta.30")
    task = asyncio.create_task(runtime.ensure_camoufox_binary())
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    process.terminate.assert_called_once_with()
    assert process.wait.await_count == (2 if termination_times_out else 1)
    assert process.kill.call_count == int(termination_times_out)
    launch.assert_awaited_once()
