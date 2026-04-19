"""Tests for justpen_browser_mcp.camoufox — lazy launcher."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from justpen_browser_mcp.camoufox import CamoufoxLauncher
from justpen_browser_mcp.errors import BinaryNotFoundError


class TestCamoufoxLauncher:
    async def test_is_running_false_before_launch(self):
        launcher = CamoufoxLauncher()
        assert launcher.is_running() is False

    async def test_get_browser_lazy_launches(self):
        launcher = CamoufoxLauncher()
        fake_browser = MagicMock(name="Browser", **{"is_connected.return_value": True})
        fake_cm = AsyncMock(name="AsyncCamoufox")
        fake_cm.__aenter__.return_value = fake_browser
        fake_cm.__aexit__.return_value = None

        with (
            patch(
                "justpen_browser_mcp.camoufox.AsyncCamoufox",
                return_value=fake_cm,
            ),
            patch.object(launcher, "_ensure_binary", new=AsyncMock()),
        ):
            browser = await launcher.get_browser()

        assert browser is fake_browser
        assert launcher.is_running() is True

    async def test_get_browser_idempotent(self):
        launcher = CamoufoxLauncher()
        fake_browser = MagicMock(name="Browser", **{"is_connected.return_value": True})
        fake_cm = AsyncMock(name="AsyncCamoufox")
        fake_cm.__aenter__.return_value = fake_browser

        with (
            patch(
                "justpen_browser_mcp.camoufox.AsyncCamoufox",
                return_value=fake_cm,
            ),
            patch.object(launcher, "_ensure_binary", new=AsyncMock()),
        ):
            b1 = await launcher.get_browser()
            b2 = await launcher.get_browser()

        assert b1 is b2
        fake_cm.__aenter__.assert_awaited_once()

    async def test_concurrent_first_calls_serialize(self):
        """Two concurrent get_browser calls should produce one launch."""
        launcher = CamoufoxLauncher()
        fake_browser = MagicMock(name="Browser", **{"is_connected.return_value": True})
        fake_cm = AsyncMock(name="AsyncCamoufox")
        fake_cm.__aenter__.return_value = fake_browser

        with (
            patch(
                "justpen_browser_mcp.camoufox.AsyncCamoufox",
                return_value=fake_cm,
            ),
            patch.object(launcher, "_ensure_binary", new=AsyncMock()),
        ):
            results = await asyncio.gather(
                launcher.get_browser(),
                launcher.get_browser(),
                launcher.get_browser(),
            )

        assert all(r is fake_browser for r in results)
        fake_cm.__aenter__.assert_awaited_once()

    async def test_shutdown_clears_browser(self):
        launcher = CamoufoxLauncher()
        fake_browser = MagicMock(name="Browser", **{"is_connected.return_value": True})
        fake_cm = AsyncMock(name="AsyncCamoufox")
        fake_cm.__aenter__.return_value = fake_browser

        with (
            patch(
                "justpen_browser_mcp.camoufox.AsyncCamoufox",
                return_value=fake_cm,
            ),
            patch.object(launcher, "_ensure_binary", new=AsyncMock()),
        ):
            await launcher.get_browser()
            assert launcher.is_running() is True
            await launcher.shutdown()

        assert launcher.is_running() is False
        fake_cm.__aexit__.assert_awaited_once()

    async def test_shutdown_idempotent(self):
        launcher = CamoufoxLauncher()
        await launcher.shutdown()
        await launcher.shutdown()
        assert launcher.is_running() is False

    async def test_relaunch_after_shutdown(self):
        launcher = CamoufoxLauncher()
        fake_browser_1 = MagicMock(name="Browser1", **{"is_connected.return_value": True})
        fake_browser_2 = MagicMock(name="Browser2", **{"is_connected.return_value": True})

        cm_1 = AsyncMock(name="cm1")
        cm_1.__aenter__.return_value = fake_browser_1
        cm_2 = AsyncMock(name="cm2")
        cm_2.__aenter__.return_value = fake_browser_2

        with (
            patch(
                "justpen_browser_mcp.camoufox.AsyncCamoufox",
                side_effect=[cm_1, cm_2],
            ),
            patch.object(launcher, "_ensure_binary", new=AsyncMock()),
        ):
            b1 = await launcher.get_browser()
            await launcher.shutdown()
            b2 = await launcher.get_browser()

        assert b1 is fake_browser_1
        assert b2 is fake_browser_2
        assert launcher.is_running() is True

    async def test_get_browser_relaunches_on_disconnect(self):
        """If the browser disconnects, get_browser should relaunch automatically."""
        launcher = CamoufoxLauncher()
        dead_browser = MagicMock(name="DeadBrowser", **{"is_connected.return_value": True})
        fresh_browser = MagicMock(name="FreshBrowser", **{"is_connected.return_value": True})

        cm_1 = AsyncMock(name="cm1")
        cm_1.__aenter__.return_value = dead_browser
        cm_2 = AsyncMock(name="cm2")
        cm_2.__aenter__.return_value = fresh_browser

        with (
            patch(
                "justpen_browser_mcp.camoufox.AsyncCamoufox",
                side_effect=[cm_1, cm_2],
            ),
            patch.object(launcher, "_ensure_binary", new=AsyncMock()),
        ):
            b1 = await launcher.get_browser()
            assert b1 is dead_browser

            # Simulate disconnect
            dead_browser.is_connected.return_value = False
            b2 = await launcher.get_browser()

        assert b2 is fresh_browser
        cm_1.__aexit__.assert_awaited_once()

    async def test_ensure_binary_passes_when_present(self):
        launcher = CamoufoxLauncher()
        with patch(
            "justpen_browser_mcp.camoufox.installed_verstr",
            return_value="135.0",
        ):
            await launcher._ensure_binary()  # type: ignore[reportPrivateUsage]  # testing the private implementation directly

    async def test_ensure_binary_runs_fetch_when_missing(self):
        launcher = CamoufoxLauncher()
        fake_proc = AsyncMock()
        fake_proc.communicate.return_value = (b"ok", b"")
        fake_proc.returncode = 0

        with (
            patch(
                "justpen_browser_mcp.camoufox.installed_verstr",
                # Real installed_verstr raises FileNotFoundError (OSError) when binary is missing
                side_effect=OSError("version.json not found"),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=fake_proc),
            ) as mock_exec,
        ):
            await launcher._ensure_binary()  # type: ignore[reportPrivateUsage]  # testing the private implementation directly

        mock_exec.assert_awaited_once()
        args = mock_exec.call_args[0]
        assert args[1] == "-m"
        assert args[2] == "camoufox"
        assert args[3] == "fetch"

    async def test_ensure_binary_raises_when_fetch_fails(self):
        launcher = CamoufoxLauncher()
        fake_proc = AsyncMock()
        fake_proc.communicate.return_value = (b"", b"network error")
        fake_proc.returncode = 1

        with (
            patch(
                "justpen_browser_mcp.camoufox.installed_verstr",
                # Real installed_verstr raises FileNotFoundError (OSError) when binary is missing
                side_effect=OSError("version.json not found"),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=fake_proc),
            ),
            pytest.raises(BinaryNotFoundError, match="network error"),
        ):
            await launcher._ensure_binary()  # type: ignore[reportPrivateUsage]  # testing the private implementation directly
