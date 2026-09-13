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
from justpen_browser_mcp.browser_runtime import ensure_camoufox_binary
from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager
from justpen_browser_mcp.tools import register_all


async def smoke(source_root: Path, *, browser: bool) -> None:
    """Check installed package identity, public contracts and a native browser round trip."""
    package = await AsyncPath(justpen_browser_mcp.__file__).resolve()
    assert not package.is_relative_to(source_root), f"Imported checkout instead of wheel: {package}"
    assert await (package.parent / "py.typed").is_file()
    expected = json.loads(await AsyncPath(source_root / "tests/fixtures/tool-input-schemas.json").read_text())
    runtime = await ensure_camoufox_binary() if browser else None
    manager = InstanceManager(BrowserServerConfig(), browser_runtime=runtime)
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
                recorder = (
                    await client.call_tool(
                        "browser_evaluate",
                        {
                            "instance": "consumer",
                            "expression": """() => {
                            window.pointerEvents = [];
                            for (const type of ['pointermove', 'pointerdown', 'pointerup']) {
                                document.addEventListener(type, e => pointerEvents.push({
                                    type, x:e.clientX, y:e.clientY, trusted:e.isTrusted, buttons:e.buttons
                                }));
                            }
                            return true;
                        }""",
                        },
                    )
                ).data
                assert recorder["status"] == "success", recorder
                for tool, arguments in (
                    ("browser_mouse_down", {}),
                    ("browser_mouse_up", {}),
                    ("browser_mouse_move_xy", {"x": 10, "y": 12}),
                    ("browser_mouse_drag_xy", {"from_x": 5, "from_y": 5, "to_x": 40, "to_y": 60}),
                ):
                    action = (await client.call_tool(tool, {"instance": "consumer", **arguments})).data
                    assert action["status"] == "success", action
                observation = (
                    await client.call_tool(
                        "browser_evaluate", {"instance": "consumer", "expression": "window.pointerEvents"}
                    )
                ).data
                assert observation["status"] == "success", observation
                events = observation["data"]["result"]
                assert events
                assert all(event["trusted"] for event in events)
                for event_type, point, buttons in (
                    ("pointerdown", [0, 0], 1),
                    ("pointerup", [0, 0], 0),
                    ("pointermove", [10, 12], 0),
                    ("pointerdown", [5, 5], 1),
                    ("pointermove", [40, 60], 1),
                    ("pointerup", [40, 60], 0),
                ):
                    assert any(
                        event["type"] == event_type
                        and [event["x"], event["y"]] == point
                        and event["buttons"] == buttons
                        for event in events
                    ), (event_type, point, events)
                destroyed = (await client.call_tool("browser_destroy_instance", {"name": "consumer"})).data
                assert destroyed["status"] == "success", destroyed
    finally:
        async with asyncio.timeout(15):
            await manager.shutdown_all()
    versions = {name: importlib.metadata.version(name) for name in ("fastmcp", "playwright", "camoufox")}
    print(
        json.dumps(
            {
                "package": str(package),
                "runtime_versions": versions,
                "browser": browser,
                "browser_version": runtime.version if runtime else None,
                "browser_installation": runtime.installation if runtime else None,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--browser", action="store_true")
    options = parser.parse_args()
    asyncio.run(smoke(options.source_root, browser=options.browser))
