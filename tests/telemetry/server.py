"""Real CLI test process with deterministic tools and no browser download."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from fastmcp import FastMCP

from justpen_browser_mcp import __main__ as entrypoint
from justpen_browser_mcp.operation_context import current_operation, mark_action_completed, mark_operation_started
from justpen_browser_mcp.responses import error_response, success_response

register_browser_tools = entrypoint.register_all


def register_fixtures(server: FastMCP, manager):
    register_browser_tools(server, manager)
    arrived = []
    barrier = asyncio.Event()
    running = {}

    @server.tool
    async def browser_telemetry_probe(mode: str = "success", label: str = "a") -> dict[str, Any]:
        mark_operation_started(f"instance-{label}", page_id=f"page-{label}")
        operation = current_operation.get()
        assert operation is not None
        running[label] = operation.id
        if mode in {"overlap", "overlap_error"}:
            arrived.append(label)
            if len(arrived) == 2:
                barrier.set()
            await asyncio.wait_for(barrier.wait(), 5)
        if mode in {"block", "timeout"}:
            mark_action_completed({"value": "sentinel-secret"}, "snapshot")
            await asyncio.Event().wait()
        if mode == "exception":
            raise ValueError("sentinel-secret")
        if mode in {"error", "overlap_error"}:
            return error_response(label, "evaluation_failed", "sentinel-secret")
        return success_response(
            label,
            {
                "arrived": list(arrived),
                "secret": "sentinel-secret" * (1000 if mode == "large" else 1),
            },
        )

    @server.tool
    async def browser_telemetry_running() -> dict[str, Any]:
        return success_response(None, {"running": dict(running)})


entrypoint._ensure_camoufox_binary = AsyncMock()
entrypoint.mcp = FastMCP("telemetry-fixture")
entrypoint.register_all = register_fixtures

if __name__ == "__main__":
    entrypoint.cli()
