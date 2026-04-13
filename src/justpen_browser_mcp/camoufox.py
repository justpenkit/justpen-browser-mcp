"""CamoufoxLauncher: lazy, idempotent, async-safe Camoufox browser lifecycle.

The launcher owns the single Camoufox browser process for the MCP server.
The browser is launched on the first call to get_browser() and shut down
either explicitly via shutdown() or automatically by ContextManager when
the last context is destroyed.

Concurrent first-calls to get_browser() are serialized via an asyncio.Lock
so only one launch happens. Subsequent calls return the cached Browser.
After shutdown(), get_browser() will launch a fresh browser on next call.

Defensive auto-fetch: if the Camoufox binary is missing on disk (e.g.,
the developer skipped `make setup` and is not in Docker), get_browser()
runs `python -m camoufox fetch` as a subprocess before launching.
"""

import asyncio
import logging
import sys

from camoufox.async_api import AsyncCamoufox
from camoufox.pkgman import installed_verstr
from playwright.async_api import Browser

from .errors import BinaryNotFoundError

logger = logging.getLogger(__name__)


class CamoufoxLauncher:
    """Lazy, idempotent launcher for the single Camoufox browser instance."""

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._browser: Browser | None = None
        self._cm: AsyncCamoufox | None = None
        self._lock = asyncio.Lock()

    def is_running(self) -> bool:
        """Return True if the browser is currently running. Does NOT trigger launch."""
        return self._browser is not None and self._browser.is_connected()

    async def get_browser(self) -> Browser:
        """Return the running Camoufox Browser, launching on first call.

        Concurrent first-calls are serialized via self._lock; only one
        actual launch happens regardless of how many callers race in.
        After shutdown(), the next call launches a fresh browser.
        """
        async with self._lock:
            if self._browser is not None and not self._browser.is_connected():
                logger.warning("Camoufox browser disconnected, cleaning up...")
                try:
                    await self._cm.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error cleaning up dead browser: {e}")
                self._cm = None
                self._browser = None
            if self._browser is None:
                await self._ensure_binary()
                logger.info("Launching Camoufox browser...")
                self._cm = AsyncCamoufox(headless=self._headless)
                self._browser = await self._cm.__aenter__()
                logger.info("Camoufox launched successfully")
            return self._browser

    async def shutdown(self) -> None:
        """Close the browser cleanly. Safe to call multiple times (idempotent)."""
        async with self._lock:
            if self._cm is not None:
                logger.info("Shutting down Camoufox browser...")
                try:
                    await self._cm.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error during Camoufox shutdown: {e}")
                self._cm = None
                self._browser = None

    async def _ensure_binary(self) -> None:
        """Verify the Camoufox binary is installed; auto-fetch if missing."""
        try:
            if installed_verstr() is not None:
                return
        except Exception as e:
            logger.debug(f"installed_verstr() raised: {e}")

        logger.warning(
            "Camoufox binary not found, fetching (one-time download ~150MB)..."
        )
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "camoufox",
            "fetch",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise BinaryNotFoundError(
                f"Failed to fetch Camoufox binary: {stderr.decode().strip()}"
            )
        logger.info("Camoufox binary fetched successfully")
