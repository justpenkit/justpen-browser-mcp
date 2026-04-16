"""Tool modules for the camoufox-mcp server.

Each module exports a `register(mcp, ctx_mgr)` function that registers
its tools with the FastMCP instance. This file imports all tool modules
to make them available as a package, but does NOT eagerly call register;
that happens in __main__.py at server startup.
"""

from . import (
    code_execution,
    cookies,
    inspection,
    interaction,
    lifecycle,
    mouse,
    navigation,
    page,
    server_tools,
    utility,
    verification,
)


def register_all(mcp, ctx_mgr, launcher) -> None:
    """Register every tool category on the FastMCP instance.

    Most tool modules only need (mcp, ctx_mgr). server_tools also needs
    the launcher for browser_status to read is_running() without
    triggering a launch.
    """
    lifecycle.register(mcp, ctx_mgr)
    cookies.register(mcp, ctx_mgr)
    navigation.register(mcp, ctx_mgr)
    interaction.register(mcp, ctx_mgr)
    mouse.register(mcp, ctx_mgr)
    inspection.register(mcp, ctx_mgr)
    verification.register(mcp, ctx_mgr)
    code_execution.register(mcp, ctx_mgr)
    utility.register(mcp, ctx_mgr)
    page.register(mcp, ctx_mgr)
    server_tools.register(mcp, ctx_mgr, launcher)
