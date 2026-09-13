"""Regenerate the reviewed MCP input-schema fixture without starting a browser."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from anyio import Path as AsyncPath
from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager
from justpen_browser_mcp.tools import register_all

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "tests/fixtures/tool-input-schemas.json"


async def update() -> None:
    """Write deterministic registered tool schemas for subsequent diff review."""
    server = FastMCP("schema-export")
    register_all(server, InstanceManager(BrowserServerConfig()))
    async with Client(server) as client:
        schemas = {tool.name: tool.model_dump(by_alias=True)["inputSchema"] for tool in await client.list_tools()}
    path = AsyncPath(SCHEMA_PATH)
    await path.write_text(json.dumps(schemas, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    asyncio.run(update())
