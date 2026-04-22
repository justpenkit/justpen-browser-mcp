"""Tool modules for the camoufox-mcp server.

Each module exports a ``register(mcp, mgr)`` function that registers its
tools with the FastMCP instance. This file imports all tool modules to make
them available as a package and provides ``register_all`` for the server
entrypoint.
"""

from fastmcp import FastMCP

from ..instance_manager import InstanceManager
from . import (
    code_execution,
    cookies,
    inspection,
    interaction,
    lifecycle,
    mouse,
    navigation,
    page,
    utility,
    verification,
)

__all__ = ["register_all"]


def register_all(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register every tool category on the FastMCP instance."""
    lifecycle.register(mcp, mgr)
    cookies.register(mcp, mgr)
    navigation.register(mcp, mgr)
    interaction.register(mcp, mgr)
    mouse.register(mcp, mgr)
    inspection.register(mcp, mgr)
    verification.register(mcp, mgr)
    code_execution.register(mcp, mgr)
    utility.register(mcp, mgr)
    page.register(mcp, mgr)
