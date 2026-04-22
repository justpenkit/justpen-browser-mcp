"""Entrypoint for `python -m justpen_browser_mcp`.

Performs one-time Camoufox binary check, builds an InstanceManager, registers
all tools, and runs the FastMCP server on stdio. SIGTERM / SIGINT trigger a
graceful shutdown that closes every live instance in parallel before the
process exits.
"""

import asyncio
import contextlib
import logging
import os
import signal
import sys

from camoufox.pkgman import installed_verstr

from .app import mcp
from .config import BrowserServerConfig
from .errors import BinaryNotFoundError
from .instance_manager import InstanceManager
from .tools import register_all

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


async def _ensure_camoufox_binary() -> None:
    """Verify the Camoufox binary is installed; auto-fetch once if missing."""
    try:
        installed_verstr()
    except (OSError, RuntimeError, ValueError) as e:
        logger.debug("installed_verstr() raised: %s", e)
    else:
        return

    logger.warning("Camoufox binary not found, fetching (one-time download ~150MB)...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "camoufox",
        "fetch",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise BinaryNotFoundError(f"Failed to fetch Camoufox binary: {stderr.decode().strip()}")
    logger.info("Camoufox binary fetched successfully")


async def main() -> None:
    """Launch the browser MCP server and keep it running on stdio."""
    config = BrowserServerConfig.from_env(os.environ)
    _setup_logging(config.log_level)

    await _ensure_camoufox_binary()

    mgr = InstanceManager(config)
    register_all(mcp, mgr)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    server_task = asyncio.create_task(mcp.run_async(), name="mcp-server")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop-signal")

    try:
        done, _ = await asyncio.wait(
            {server_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done and not server_task.done():
            logger.info("Received shutdown signal, stopping MCP server...")
            server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server_task
    finally:
        await mgr.shutdown_all()


def cli() -> None:
    """Sync entrypoint for the `justpen-browser-mcp` console script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
