"""Shared pytest fixtures — InstanceManager with mocked Camoufox."""

from contextlib import AsyncExitStack
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager


@pytest.fixture
def mock_launch(monkeypatch):
    """Patch launch_instance to return a fake stack + MagicMock BrowserContext.

    Each call yields a fresh context so tests can assert per-instance isolation.
    The returned stack's aclose is a real AsyncExitStack so tests can verify
    clean teardown without touching Playwright.
    """
    launched: list[dict[str, Any]] = []

    async def _fake_launch(**kwargs: Any):
        stack = AsyncExitStack()
        await stack.__aenter__()
        ctx = MagicMock()
        ctx.pages = []
        ctx.on = MagicMock()
        ctx.cookies = AsyncMock(return_value=[])
        ctx.close = AsyncMock()
        ctx.new_page = AsyncMock()
        launched.append({"kwargs": kwargs, "ctx": ctx})
        return stack, ctx

    monkeypatch.setattr("justpen_browser_mcp.instance_manager.launch_instance", _fake_launch)
    return launched


@pytest.fixture
async def manager(mock_launch):
    cfg = BrowserServerConfig(log_level="INFO", max_instances=10)
    mgr = InstanceManager(cfg)
    yield mgr
    await mgr.shutdown_all()
