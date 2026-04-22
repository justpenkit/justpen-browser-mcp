"""Shared fixtures for tool-level tests.

Provides ``mcp_client`` (a FastMCP in-process test client) and
``mock_mgr`` / ``mock_ctx_mgr`` (an InstanceManager mock) so that every
tool module can be tested without a live browser.
"""

import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client


class _AsyncLockContext:
    """Minimal async context manager that acts like asyncio.Lock in a ``with`` block."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _ConnectedClient:
    """Thin wrapper that keeps the Client connected for the lifetime of the fixture."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def call_tool(self, name: str, args: dict | None = None):
        async with self._client:
            return await self._client.call_tool(name, args or {})


@pytest.fixture
def mock_mgr():
    """Return a MagicMock shaped like InstanceManager.

    All async methods (get, active_page) are AsyncMocks.  Sync methods
    (lock_for, state, get_modal_states, consume_modal_state, set_active_page)
    are MagicMocks.  Tests can override individual attributes as needed.
    """
    mgr = MagicMock()
    mgr.get = AsyncMock(return_value=MagicMock())
    mgr.active_page = AsyncMock()
    mgr.lock_for = MagicMock(return_value=_AsyncLockContext())
    mgr.state = MagicMock(return_value=MagicMock())
    mgr.get_modal_states = MagicMock(return_value=[])
    mgr.consume_modal_state = MagicMock(return_value=None)
    mgr.set_active_page = MagicMock()
    return mgr


# Alias so existing test signatures that say ``mock_ctx_mgr`` still resolve.
@pytest.fixture
def mock_ctx_mgr(mock_mgr):
    """Alias for mock_mgr — keeps existing test signatures working."""
    return mock_mgr


@pytest.fixture
def mcp_client(mock_mgr, request):
    """In-process FastMCP client with the calling test's tool module registered.

    The fixture inspects the test module name (e.g. ``test_navigation``) to
    derive the corresponding tool module (``navigation``) and registers it on a
    fresh FastMCP instance.  Returns a _ConnectedClient wrapper so tests can
    call ``await mcp_client.call_tool(...)`` without managing context managers.
    """
    mcp = FastMCP("test")

    # Derive tool module from test module name, e.g. test_navigation → navigation
    test_module_name = request.module.__name__  # e.g. tests.tools.test_navigation
    short_name = test_module_name.rsplit(".", 1)[-1]  # e.g. test_navigation
    tool_module_name = short_name[len("test_") :]  # e.g. navigation

    try:
        tool_mod = importlib.import_module(f"justpen_browser_mcp.tools.{tool_module_name}")
        tool_mod.register(mcp, mock_mgr)
    except (ImportError, AttributeError):
        pass  # Module not found or has no register() — tests will fail naturally

    return _ConnectedClient(Client(mcp))
