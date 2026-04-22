"""Tool modules for the camoufox-mcp server.

Each module exports a ``register`` function that registers its tools with the
FastMCP instance.  This file imports all tool modules to make them available as
a package, but does NOT eagerly call register; that happens in __main__.py at
server startup.

NOTE: ``register_all`` is a **temporary stub** kept here so that downstream
modules that reference it do not break before Task 8 (delete deprecated
modules) and Task 9 (__main__.py rewire) land.  It will be removed or replaced
in those tasks.
"""

# Lifecycle is the first module to be fully migrated to the new InstanceManager
# API.  Import it explicitly so it is importable without triggering the still-
# broken legacy imports (context_manager, camoufox) that will be removed in
# Task 8.
from . import lifecycle

__all__ = ["lifecycle"]
