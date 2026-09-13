"""Tools for listing and explicitly saving retained browser downloads."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from playwright.async_api import Error as PlaywrightError

from ..errors import BrowserMcpError, DownloadFailedError
from ..operation_context import mark_artifact_write_started, mark_operation_started
from ..responses import error_response, success_response

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..downloads import DownloadRegistry
    from ..instance_manager import InstanceManager


def _registry(mgr: InstanceManager, instance: str) -> DownloadRegistry:
    return mgr.state(instance).downloads


def _register_browser_downloads(mcp: FastMCP, mgr: InstanceManager) -> None:
    @mcp.tool
    async def browser_downloads(
        instance: str, *, page_id: str | None = None, after: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        """List retained download evidence, optionally filtered by originating page."""
        try:
            mgr.get(instance)
            result = _registry(mgr, instance).page(after=after, limit=limit, page_id=page_id)
            data = {**result, "downloads": result["items"]}
            data.pop("items")
            return success_response(instance, data=data)
        except BrowserMcpError as error:
            return error_response(instance, error.error_type, str(error))
        except ValueError as error:
            return error_response(instance, "invalid_params", str(error))
        except Exception as error:
            logger.exception("browser_downloads failed")
            return error_response(instance, "internal_error", str(error))


def _register_browser_download_save(mcp: FastMCP, mgr: InstanceManager) -> None:
    @mcp.tool
    async def browser_download_save(instance: str, download_id: str, path: str) -> dict[str, Any]:
        """Copy a retained browser download to an explicit server path."""
        try:
            record = mgr.get(instance)
            async with mgr.lock_for(instance):
                registry = _registry(mgr, instance)
                download_record = registry.pin(download_id)
                try:
                    mark_operation_started(record.instance_id, page_id=download_record.page_id)
                    mark_artifact_write_started()
                    try:
                        await download_record.download.save_as(path)
                    except (PlaywrightError, OSError, RuntimeError) as error:
                        registry.finish(download_id, path=path, failure=str(error))
                        raise DownloadFailedError(f"Could not save download {download_id!r}: {error}") from error
                    registry.finish(download_id, path=path)
                    return success_response(instance, data={"download_id": download_id, "path": path})
                finally:
                    registry.unpin(download_id)
        except BrowserMcpError as error:
            return error_response(instance, error.error_type, str(error))
        except Exception as error:
            logger.exception("browser_download_save failed")
            return error_response(instance, "internal_error", str(error))


def register(mcp: FastMCP, mgr: InstanceManager) -> None:
    """Register download evidence tools."""
    _register_browser_downloads(mcp, mgr)
    _register_browser_download_save(mcp, mgr)
