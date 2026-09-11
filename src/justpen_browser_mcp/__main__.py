"""Entrypoint for `python -m justpen_browser_mcp`.

Performs one-time Camoufox binary check, builds an InstanceManager, registers
all tools, and runs the FastMCP server on stdio or HTTP. SIGTERM / SIGINT trigger a
graceful shutdown that closes every live instance in parallel before the
process exits.
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Any

from .app import mcp
from .browser_runtime import ensure_camoufox_binary as _ensure_camoufox_binary
from .cli import build_config
from .config import BrowserServerConfig
from .instance_manager import InstanceManager
from .tools import register_all

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _run_kwargs(config: BrowserServerConfig) -> dict[str, Any]:
    """Build run_async kwargs from config: empty for stdio, host/port for http."""
    if config.transport == "http":
        return {"transport": "http", "host": config.host, "port": config.port}
    return {}


async def main() -> None:
    """Launch the browser MCP server using the configured transport."""
    config = build_config(sys.argv[1:], os.environ)
    _setup_logging(config.log_level)

    await _ensure_camoufox_binary()

    mgr = InstanceManager(config)
    register_all(mcp, mgr)
    mgr.start_reaper()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    server_task = asyncio.create_task(mcp.run_async(**_run_kwargs(config)), name="mcp-server")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop-signal")

    try:
        done, _ = await asyncio.wait(
            {server_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done and not server_task.done():
            logger.info("Received shutdown signal, stopping MCP server...")
            server_task.cancel()
            # Wait for shutdown without suppressing cancellation of main itself.
            await asyncio.wait({server_task})
            if server_task.cancelled():
                return
        await server_task
    finally:
        server_task.cancel()
        stop_task.cancel()
        try:
            await asyncio.gather(server_task, stop_task, return_exceptions=True)
        finally:
            await mgr.stop_reaper()
            await mgr.shutdown_all()


def cli() -> None:
    """Sync entrypoint for the `justpen-browser-mcp` console script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
