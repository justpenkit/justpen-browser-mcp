"""Entrypoint for `python -m justpen_browser_mcp`.

Registers all tools then starts the FastMCP server on stdio transport.
"""

import asyncio
import logging
import os
import sys

from playwright.async_api import Error as PlaywrightError

from .app import mcp
from .camoufox import CamoufoxLauncher
from .config import BrowserServerConfig
from .context_manager import ContextManager
from .errors import BrowserMcpError
from .tools import register_all

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,  # never stdout — that's the MCP protocol channel
    )


async def main() -> None:
    """Launch the browser MCP server and keep it running on stdio."""
    config = BrowserServerConfig.from_env(os.environ)
    _setup_logging(config.log_level)

    launcher = CamoufoxLauncher(headless=config.headless)
    ctx_mgr = ContextManager(launcher)

    register_all(mcp, ctx_mgr, launcher)

    try:
        await mcp.run_async()
    finally:
        for name in ctx_mgr.list_names():
            try:
                await ctx_mgr.destroy(name)
            except (PlaywrightError, BrowserMcpError, OSError, RuntimeError) as e:
                logger.warning("Error destroying context '%s' on shutdown: %s", name, e)
        await launcher.shutdown()


def cli() -> None:
    """Sync entrypoint for the `justpen-browser-mcp` console script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
