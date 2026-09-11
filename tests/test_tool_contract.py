"""Preserve the public input schemas captured before the framework migration."""

import json
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager
from justpen_browser_mcp.tools import register_all


async def test_all_43_tool_input_schemas_match_the_existing_application():
    expected = json.loads((Path(__file__).parent / "fixtures/tool-input-schemas.json").read_text())
    server = FastMCP("contract")
    register_all(server, InstanceManager(BrowserServerConfig()))
    async with Client(server) as client:
        actual = {tool.name: tool.model_dump(by_alias=True)["inputSchema"] for tool in await client.list_tools()}
    assert len(actual) == 43
    assert actual == expected
