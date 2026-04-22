"""Tool modules for the camoufox-mcp server.

Each module exports a ``register`` function that registers its tools with the
FastMCP instance.  This file imports all tool modules to make them available as
a package, but does NOT eagerly call register; that happens in __main__.py at
server startup.
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
    utility,
    verification,
)

__all__ = [
    "code_execution",
    "cookies",
    "inspection",
    "interaction",
    "lifecycle",
    "mouse",
    "navigation",
    "page",
    "utility",
    "verification",
]
