"""Instance lifecycle tools: create, destroy, list."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from ..errors import BrowserMcpError
from ..responses import error_response, success_response

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..instance_manager import InstanceManager

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register instance-lifecycle tools on the MCP server."""

    @mcp.tool
    async def browser_create_instance(
        name: str,
        *,
        profile_dir: str | None = None,
        headless: bool | Literal["virtual"] = True,
        proxy: dict[str, str] | None = None,
        humanize: bool | float = True,
        window: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        """Create a new isolated Camoufox browser instance.

        Each instance runs in its own Camoufox process with its own BrowserForge
        fingerprint and (if `profile_dir` is provided) its own on-disk profile.
        Ephemeral instances (profile_dir=None) leave no trace after destroy.
        """
        try:
            await mgr.create(
                name,
                profile_dir=profile_dir,
                headless=headless,
                proxy=proxy,
                humanize=humanize,
                window=window,
            )
        except BrowserMcpError as e:
            return error_response(name, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_create_instance failed for %r", name)
            return error_response(name, "internal_error", str(e))
        summaries = await mgr.list()
        summary = next(s for s in summaries if s["name"] == name)
        return success_response(instance=name, data=summary)

    @mcp.tool
    async def browser_destroy_instance(name: str) -> dict[str, Any]:
        """Destroy an instance and free its resources. Persistent profile dir survives on disk."""
        try:
            await mgr.destroy(name)
        except BrowserMcpError as e:
            return error_response(name, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_destroy_instance failed for %r", name)
            return error_response(name, "internal_error", str(e))
        return success_response(instance=name)

    @mcp.tool
    async def browser_list_instances() -> dict[str, Any]:
        """Return summaries of all live instances."""
        try:
            summaries = await mgr.list()
        except Exception as e:
            logger.exception("browser_list_instances failed")
            return error_response(None, "internal_error", str(e))
        return success_response(instance=None, data={"instances": summaries})
