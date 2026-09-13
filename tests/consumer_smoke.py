"""Standalone acceptance test executed outside the checkout against an installed wheel."""

import argparse
import asyncio
import importlib.metadata
import json
from pathlib import Path

from anyio import Path as AsyncPath
from fastmcp import FastMCP
from fastmcp.client import Client

import justpen_browser_mcp
from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager
from justpen_browser_mcp.tools import register_all


async def smoke(source_root: Path, *, browser: bool) -> None:
    """Check installed package identity, public contracts and a native browser round trip."""
    package = await AsyncPath(justpen_browser_mcp.__file__).resolve()
    assert not package.is_relative_to(source_root), f"Imported checkout instead of wheel: {package}"
    assert await (package.parent / "py.typed").is_file()
    expected = json.loads(await AsyncPath(source_root / "tests/fixtures/tool-input-schemas.json").read_text())
    manager = InstanceManager(BrowserServerConfig())
    server = FastMCP("consumer")
    register_all(server, manager)
    try:
        async with asyncio.timeout(60), Client(server) as client:
            schemas = {tool.name: tool.model_dump(by_alias=True)["inputSchema"] for tool in await client.list_tools()}
            assert schemas == expected
            assert len(schemas) == 46
            health = (await client.call_tool("browser_health", {})).data
            assert health["status"] == "success", health
            assert health["data"]["instance_count"] == 0
            if browser:
                created = (await client.call_tool("browser_create_instance", {"name": "consumer"})).data
                assert created["status"] == "success", created
                navigation = (
                    await client.call_tool(
                        "browser_navigate",
                        {"instance": "consumer", "url": "data:text/html,<h1>Consumer</h1>"},
                    )
                ).data
                assert navigation["status"] == "success", navigation
                snapshot = (await client.call_tool("browser_snapshot", {"instance": "consumer"})).data
                assert snapshot["status"] == "success", snapshot
                assert 'heading "Consumer"' in snapshot["data"]["snapshot"]
                destroyed = (await client.call_tool("browser_destroy_instance", {"name": "consumer"})).data
                assert destroyed["status"] == "success", destroyed
    finally:
        async with asyncio.timeout(15):
            await manager.shutdown_all()
    versions = {name: importlib.metadata.version(name) for name in ("fastmcp", "playwright", "camoufox")}
    print(json.dumps({"package": str(package), "runtime_versions": versions, "browser": browser}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--browser", action="store_true")
    options = parser.parse_args()
    asyncio.run(smoke(options.source_root, browser=options.browser))
