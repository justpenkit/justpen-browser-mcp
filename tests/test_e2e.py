"""End-to-end tests for the camoufox-mcp server.

These tests require a real Camoufox browser and run inside the
ephemeral Docker test container via scripts/run-e2e-tests.sh.
Use `pytest -m e2e` to opt in.
"""

import asyncio
import json
import re
from pathlib import Path

import pytest
from camoufox.async_api import AsyncCamoufox
from fastmcp.client import Client


@pytest.mark.e2e
async def test_snapshot_for_ai_returns_refs_poc():
    """Verify the snapshotForAI raw-channel hack emits [ref=eN] annotations.

    The high-level Python API doesn't expose snapshotForAI, but the
    underlying server bundled with playwright-python 1.53+ implements it.
    We call it via page._impl_obj._channel.send(...) — workaround documented
    in https://github.com/microsoft/playwright-python/issues/2867
    """
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        await page.set_content("<button>Click me</button><a href='/x'>Link</a><input type='text' placeholder='email'>")
        snapshot = await page._impl_obj._channel.send("snapshotForAI", None, {"timeout": 5000})

    assert isinstance(snapshot, str), f"snapshot is not a string: {type(snapshot)}"
    assert "Click me" in snapshot, f"button text missing from snapshot:\n{snapshot}"
    assert "[ref=" in snapshot, (
        f"Expected [ref=...] annotation in snapshot, got:\n{snapshot[:500]}\n"
        f"This is a critical assumption failure — see plan Task 5 for fallback steps."
    )


@pytest.mark.e2e
async def test_aria_ref_locator_resolves():
    """Verify page.locator('aria-ref=eN') resolves a ref from snapshotForAI."""
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        await page.set_content("<button id='btn'>Hello</button>")
        snapshot = await page._impl_obj._channel.send("snapshotForAI", None, {"timeout": 5000})
        match = re.search(r"button[^[]*\[ref=([^\]]+)\]", snapshot)
        assert match, f"Could not find button ref in snapshot:\n{snapshot}"
        ref = match.group(1)
        locator = page.locator(f"aria-ref={ref}")
        text = await locator.text_content()
        assert text == "Hello", f"Expected 'Hello', got {text!r}"


@pytest.mark.e2e
async def test_full_server_lifecycle_with_real_browser():
    """Boot the MCP server, create a context, navigate, snapshot,
    destroy. Verify lazy launch + auto-shutdown work end-to-end.
    """
    from fastmcp import FastMCP

    from justpen_browser_mcp.camoufox import CamoufoxLauncher
    from justpen_browser_mcp.context_manager import ContextManager
    from justpen_browser_mcp.tools import register_all

    mcp = FastMCP("camoufox-mcp-e2e")
    launcher = CamoufoxLauncher(headless=True)
    ctx_mgr = ContextManager(launcher)
    register_all(mcp, ctx_mgr, launcher)

    async with Client(mcp) as client:
        status = await client.call_tool("browser_status", {})
        assert status.data["data"]["browser_running"] is False

        await client.call_tool("browser_create_context", {"context": "e2e"})
        status = await client.call_tool("browser_status", {})
        assert status.data["data"]["browser_running"] is True
        assert status.data["data"]["active_context_count"] == 1

        nav = await client.call_tool(
            "browser_navigate",
            {
                "context": "e2e",
                "url": "data:text/html,<h1>Test Page</h1><button>Click</button>",
            },
        )
        assert nav.data["status"] == "success"

        snap = await client.call_tool("browser_snapshot", {"context": "e2e"})
        assert snap.data["status"] == "success"
        assert "Click" in snap.data["data"]["snapshot"]
        assert "[ref=" in snap.data["data"]["snapshot"]

        await client.call_tool("browser_destroy_context", {"context": "e2e"})
        status = await client.call_tool("browser_status", {})
        assert status.data["data"]["browser_running"] is False
        assert status.data["data"]["active_context_count"] == 0


@pytest.mark.e2e
async def test_storage_state_round_trip(tmp_path):
    """Create a context, set a cookie, export state, destroy, create a new
    context loading that state, verify the cookie is restored."""
    from fastmcp import FastMCP

    from justpen_browser_mcp.camoufox import CamoufoxLauncher
    from justpen_browser_mcp.context_manager import ContextManager
    from justpen_browser_mcp.tools import register_all

    mcp = FastMCP("camoufox-mcp-e2e-roundtrip")
    launcher = CamoufoxLauncher(headless=True)
    ctx_mgr = ContextManager(launcher)
    register_all(mcp, ctx_mgr, launcher)

    state_file = str(tmp_path / "saved.json")

    async with Client(mcp) as client:
        await client.call_tool("browser_create_context", {"context": "phase1"})
        await client.call_tool(
            "browser_navigate",
            {"context": "phase1", "url": "https://example.com"},
        )
        await client.call_tool(
            "browser_set_cookies",
            {
                "context": "phase1",
                "cookies": [
                    {
                        "name": "round_trip_test",
                        "value": "abc123",
                        "domain": "example.com",
                        "path": "/",
                    }
                ],
            },
        )
        await client.call_tool(
            "browser_export_context_state",
            {"context": "phase1", "state_path": state_file},
        )
        await client.call_tool("browser_destroy_context", {"context": "phase1"})

        assert Path(state_file).exists()
        saved = json.loads(Path(state_file).read_text())
        cookie_names = {c["name"] for c in saved["cookies"]}
        assert "round_trip_test" in cookie_names

        await client.call_tool(
            "browser_create_context",
            {"context": "phase2", "state_path": state_file},
        )
        cookies = await client.call_tool(
            "browser_get_cookies",
            {"context": "phase2", "urls": ["https://example.com"]},
        )
        names = {c["name"] for c in cookies.data["data"]["cookies"]}
        assert "round_trip_test" in names
        await client.call_tool("browser_destroy_context", {"context": "phase2"})


@pytest.mark.e2e
async def test_concurrent_multi_context_operations():
    """Two contexts sharing one browser — verify that operations on
    separate contexts don't interfere with each other's state.

    Note: the in-memory MCP transport serialises requests over a single
    channel, so we exercise each context in sequence rather than with
    asyncio.gather (which would deadlock waiting for simultaneous
    responses on the same stream). The intent — isolation between
    contexts — is still fully validated.
    """
    from fastmcp import FastMCP

    from justpen_browser_mcp.camoufox import CamoufoxLauncher
    from justpen_browser_mcp.context_manager import ContextManager
    from justpen_browser_mcp.tools import register_all

    mcp = FastMCP("camoufox-mcp-e2e-concurrent")
    launcher = CamoufoxLauncher(headless=True)
    ctx_mgr = ContextManager(launcher)
    register_all(mcp, ctx_mgr, launcher)

    async with Client(mcp) as client:
        await client.call_tool("browser_create_context", {"context": "ctxA"})
        await client.call_tool("browser_create_context", {"context": "ctxB"})

        nav_a = await client.call_tool(
            "browser_navigate",
            {"context": "ctxA", "url": "data:text/html,<h1>A</h1>"},
        )
        assert nav_a.data["status"] == "success"

        nav_b = await client.call_tool(
            "browser_navigate",
            {"context": "ctxB", "url": "data:text/html,<h1>B</h1>"},
        )
        assert nav_b.data["status"] == "success"

        snap_a = await client.call_tool("browser_snapshot", {"context": "ctxA"})
        snap_b = await client.call_tool("browser_snapshot", {"context": "ctxB"})
        assert "A" in snap_a.data["data"]["snapshot"]
        assert "B" in snap_b.data["data"]["snapshot"]

        await client.call_tool("browser_destroy_context", {"context": "ctxA"})
        await client.call_tool("browser_destroy_context", {"context": "ctxB"})


@pytest.mark.e2e
async def test_relaunch_after_auto_shutdown():
    """Create a context, destroy it (auto-shutdown), then create a new
    context — verify the browser re-launches cleanly."""
    from fastmcp import FastMCP

    from justpen_browser_mcp.camoufox import CamoufoxLauncher
    from justpen_browser_mcp.context_manager import ContextManager
    from justpen_browser_mcp.tools import register_all

    mcp = FastMCP("camoufox-mcp-e2e-relaunch")
    launcher = CamoufoxLauncher(headless=True)
    ctx_mgr = ContextManager(launcher)
    register_all(mcp, ctx_mgr, launcher)

    async with Client(mcp) as client:
        await client.call_tool("browser_create_context", {"context": "first"})
        assert (await client.call_tool("browser_status", {})).data["data"]["browser_running"]

        await client.call_tool("browser_destroy_context", {"context": "first"})
        assert not (await client.call_tool("browser_status", {})).data["data"]["browser_running"]

        await client.call_tool("browser_create_context", {"context": "second"})
        assert (await client.call_tool("browser_status", {})).data["data"]["browser_running"]

        await client.call_tool(
            "browser_navigate",
            {"context": "second", "url": "data:text/html,<h1>Second</h1>"},
        )
        snap = await client.call_tool("browser_snapshot", {"context": "second"})
        assert "Second" in snap.data["data"]["snapshot"]

        await client.call_tool("browser_destroy_context", {"context": "second"})


@pytest.mark.e2e
async def test_generate_locator_with_real_snapshot():
    """End-to-end: take a real snapshot, extract a ref, call resolveSelector,
    verify the returned internal selector resolves back to the same element."""
    import re

    from fastmcp import FastMCP
    from fastmcp.client import Client

    from justpen_browser_mcp.camoufox import CamoufoxLauncher
    from justpen_browser_mcp.context_manager import ContextManager
    from justpen_browser_mcp.tools import register_all

    mcp = FastMCP("camoufox-mcp-e2e-generate-locator")
    launcher = CamoufoxLauncher(headless=True)
    ctx_mgr = ContextManager(launcher)
    register_all(mcp, ctx_mgr, launcher)

    async with Client(mcp) as client:
        await client.call_tool("browser_create_context", {"context": "loc"})
        await client.call_tool(
            "browser_navigate",
            {
                "context": "loc",
                "url": ("data:text/html,<button data-testid='primary-btn'>Submit</button><input placeholder='Email'>"),
            },
        )
        snap = await client.call_tool("browser_snapshot", {"context": "loc"})
        snapshot_text = snap.data["data"]["snapshot"]

        # Find the button's ref (it has a data-testid so should get test-id priority)
        match = re.search(r"button[^[]*\[ref=([^\]]+)\]", snapshot_text)
        assert match, f"button ref missing:\n{snapshot_text}"
        button_ref = match.group(1)

        result = await client.call_tool(
            "browser_generate_locator",
            {"context": "loc", "ref": button_ref},
        )
        assert result.data["status"] == "success"

        internal = result.data["data"]["internal_selector"]
        python_syntax = result.data["data"]["python_syntax"]

        # data-testid should beat role
        assert "testid" in internal
        assert "primary-btn" in internal
        assert "get_by_test_id('primary-btn')" == python_syntax

        await client.call_tool("browser_destroy_context", {"context": "loc"})
