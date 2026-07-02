"""Instance lifecycle tools: create, destroy, list."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from ..errors import BrowserMcpError
from ..instance_manager import summarize_instance
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
        headless: bool | Literal["virtual"] | None = None,
        proxy: dict[str, str] | None = None,
        humanize: bool | float | None = None,
        window: tuple[int, int] | None = None,
        block_images: bool | None = None,
        block_webrtc: bool | None = None,
        block_webgl: bool | None = None,
        camoufox_os: tuple[str, ...] | None = None,
        locale: str | None = None,
        geoip: bool | None = None,
        firefox_user_prefs: dict[str, Any] | None = None,
        camoufox_args: tuple[str, ...] | None = None,
        enable_cache: bool | None = None,
        ff_version: int | None = None,
    ) -> dict[str, Any]:
        """Create a new isolated Camoufox browser instance.

        Each instance runs in its own Camoufox process with its own BrowserForge
        fingerprint and (if `profile_dir` is provided) its own on-disk profile.
        Ephemeral instances (profile_dir=None) leave no trace after destroy.

        Every camoufox-related parameter defaults to None, meaning "use the
        server-level config default"; passing a non-None value overrides that
        default for this instance only.
        """
        try:
            record = await mgr.create(
                name,
                profile_dir=profile_dir,
                headless=headless,
                proxy=proxy,
                humanize=humanize,
                window=window,
                block_images=block_images,
                block_webrtc=block_webrtc,
                block_webgl=block_webgl,
                camoufox_os=camoufox_os,
                locale=locale,
                geoip=geoip,
                firefox_user_prefs=firefox_user_prefs,
                camoufox_args=camoufox_args,
                enable_cache=enable_cache,
                ff_version=ff_version,
            )
        except BrowserMcpError as e:
            return error_response(name, e.error_type, str(e))
        except Exception as e:
            logger.exception("browser_create_instance failed for %r", name)
            return error_response(name, "internal_error", str(e))
        return success_response(instance=name, data=summarize_instance(record))

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
