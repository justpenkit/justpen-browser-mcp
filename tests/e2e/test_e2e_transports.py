"""Exercise the installed entrypoint over stdio and HTTP with a real browser."""

import asyncio
import os
import socket
import sys
from pathlib import Path

import pytest
from fastmcp.client import Client
from fastmcp.client.transports import StdioTransport

from .conftest import call

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio, pytest.mark.timeout(90)]


async def _exercise_browser(client, test_site):
    tools = await client.list_tools()
    assert len(tools) == 43
    health = await call(client, "browser_health")
    assert health["status"] == "success", health
    assert health["data"]["instance_count"] == 0
    created = await call(client, "browser_create_instance", {"name": "transport"})
    assert created["status"] == "success", created
    navigated = await call(client, "browser_navigate", {"instance": "transport", "url": test_site + "/index.html"})
    assert navigated["status"] == "success", navigated
    snapshot = await call(client, "browser_snapshot", {"instance": "transport"})
    assert snapshot["status"] == "success", snapshot
    assert 'heading "Home"' in snapshot["data"]["snapshot"]
    destroyed = await call(client, "browser_destroy_instance", {"name": "transport"})
    assert destroyed["status"] == "success", destroyed


def _environment():
    return {key: value for key, value in os.environ.items() if not key.startswith("BROWSER_MCP_")}


async def test_installed_stdio_entrypoint(test_site):
    transport = StdioTransport(
        command=str(Path(sys.executable).with_name("justpen-browser-mcp")),
        args=["--transport", "stdio"],
        env=_environment(),
        keep_alive=False,
    )
    async with Client(transport) as client:
        await _exercise_browser(client, test_site)


async def test_installed_http_entrypoint(test_site, tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    log_path = tmp_path / "server.log"
    with log_path.open("wb") as log:
        process = await asyncio.create_subprocess_exec(
            str(Path(sys.executable).with_name("justpen-browser-mcp")),
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            env=_environment(),
            stdout=log,
            stderr=log,
        )
        try:
            async with asyncio.timeout(20):
                while True:
                    assert process.returncode is None, log_path.read_text()
                    try:
                        _, writer = await asyncio.open_connection("127.0.0.1", port)
                    except OSError:
                        await asyncio.sleep(0.1)
                    else:
                        writer.close()
                        await writer.wait_closed()
                        break
            async with Client(f"http://127.0.0.1:{port}/mcp") as client:
                await _exercise_browser(client, test_site)
        finally:
            if process.returncode is None:
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except TimeoutError:
                process.kill()
                await process.wait()
        assert process.returncode == 0, log_path.read_text()
