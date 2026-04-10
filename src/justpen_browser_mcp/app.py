"""FastMCP server instance singleton.

Defined in its own module to avoid circular imports between tool
modules and the server orchestration code in __main__.py.
"""

from fastmcp import FastMCP

mcp = FastMCP("camoufox-mcp")
