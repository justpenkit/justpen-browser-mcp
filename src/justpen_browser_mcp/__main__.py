"""Entrypoint for `python -m justpen_browser_mcp`.

Registers all tools then starts the FastMCP server on stdio transport.
"""

import asyncio
import logging
import os
import sys

from .app import mcp
from .camoufox import CamoufoxLauncher
from .config import BrowserServerConfig
from .context_manager import ContextManager
from .tools import register_all


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,  # never stdout — that's the MCP protocol channel
    )


async def main() -> None:
    config = BrowserServerConfig.from_env(os.environ)
    _setup_logging(config.log_level)

    launcher = CamoufoxLauncher(headless=config.headless)
    ctx_mgr = ContextManager(launcher)

    register_all(mcp, ctx_mgr, launcher)

    try:
        await mcp.run_async()
    finally:
        for name in list(ctx_mgr._contexts.keys()):
            try:
                await ctx_mgr.destroy(name)
            except Exception as e:
                logging.warning("Error destroying context '%s' on shutdown: %s", name, e)
        await launcher.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
