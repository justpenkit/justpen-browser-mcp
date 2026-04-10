"""Shared fixtures for browser_mcp tests.

The `mcp_client` fixture builds a fresh FastMCP instance + mocked
ContextManager and returns a FastMCP test client. Tools are registered
on the fresh instance so tests don't interfere with each other.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.tools import register_all


@pytest.fixture
def mock_ctx_mgr():
    """A mocked ContextManager whose methods are AsyncMocks ready to be
    configured per-test."""
    mgr = MagicMock(name="ContextManager")
    mgr.create = AsyncMock()
    mgr.get = AsyncMock()
    mgr.destroy = AsyncMock()
    mgr.list = AsyncMock(return_value=[])
    mgr.export_state = AsyncMock()
    mgr.load_state = AsyncMock()
    mgr.active_page = AsyncMock()
    mgr.lock_for = MagicMock()
    mgr.lock_for.return_value = asyncio.Lock()
    mgr._contexts = {}
    return mgr


@pytest.fixture
def mock_launcher():
    """A mocked CamoufoxLauncher."""
    launcher = MagicMock(name="CamoufoxLauncher")
    launcher.is_running = MagicMock(return_value=False)
    launcher.shutdown = AsyncMock()
    return launcher


@pytest.fixture
async def mcp_client(mock_ctx_mgr, mock_launcher):
    """A FastMCP test client with all tools registered against mocked deps."""
    mcp = FastMCP("camoufox-mcp-test")

    register_all(mcp, mock_ctx_mgr, mock_launcher)

    async with Client(mcp) as client:
        yield client
