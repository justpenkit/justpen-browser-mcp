"""E2e harness: local static site + real Camoufox driven through a FastMCP client.

Fixtures:
- ``test_site`` (session-scoped): serves ``tests/e2e/pages/`` over a
  ``ThreadingHTTPServer`` bound to an ephemeral port on 127.0.0.1, yielding
  the base URL.
- ``e2e_client`` (function-scoped): a real ``InstanceManager`` + a fresh
  ``FastMCP`` server with every tool registered via ``register_all``, wrapped
  in a connected FastMCP ``Client``. Tears down by shutting down all browser
  instances.

Helper:
- ``call(client, name, args)``: invokes a tool and returns the unwrapped
  response-envelope dict (``{"status": ..., "instance": ..., "data": {...}}``
  or the error shape), mirroring the ``.data`` unwrapping used throughout
  ``tests/tools``.
"""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager
from justpen_browser_mcp.tools import register_all

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

PAGES_DIR = Path(__file__).parent / "pages"


class _Handler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler pinned to HTTP/1.0.

    Forcing HTTP/1.0 disables keep-alive, so every connection closes right
    after its response. Without this, a browser-held keep-alive socket can
    outlive the server (closed via ``shutdown()``/``server_close()``) and get
    garbage-collected at an arbitrary later point, which pytest reports as an
    unraisable ``ResourceWarning`` (promoted to an error by this project's
    ``filterwarnings = ["error"]``) attributed to an unrelated test.
    """

    protocol_version = "HTTP/1.0"


@pytest.fixture(scope="session")
def test_site() -> Iterator[str]:
    """Serve ``tests/e2e/pages/`` on an ephemeral localhost port for the whole session."""
    handler = partial(_Handler, directory=str(PAGES_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
async def e2e_client() -> AsyncIterator[Client[Any]]:
    """Yield a connected FastMCP client backed by a real InstanceManager."""
    cfg = BrowserServerConfig(log_level="INFO", max_instances=5)
    mgr = InstanceManager(cfg)
    mcp = FastMCP("e2e")
    register_all(mcp, mgr)
    client = Client(mcp)
    try:
        async with client:
            yield client
    finally:
        await mgr.shutdown_all()


async def call(client: Client[Any], name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call an MCP tool and return the unwrapped response-envelope dict.

    Returns the ``CallToolResult.data`` payload, i.e. the raw envelope shape
    produced by ``justpen_browser_mcp.responses`` — either
    ``{"status": "success", "instance": ..., "data": {...}}`` or the error
    shape ``{"status": "error", "instance": ..., "error_type": ..., "message": ...}``.
    """
    result = await client.call_tool(name, args or {})
    return result.data
