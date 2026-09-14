"""Entrypoint for `python -m justpen_browser_mcp`.

Performs one-time Camoufox binary check, builds an InstanceManager, registers
all tools, and runs the FastMCP server on stdio or HTTP. SIGTERM / SIGINT trigger a
graceful shutdown that closes every live instance in parallel before the
process exits.
"""

import asyncio
import logging
import os
import signal
import sys
from importlib.metadata import version
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context, attach, detach
from starlette.middleware import Middleware

from .app import mcp
from .browser_runtime import BrowserRuntime, ensure_camoufox_binary as _ensure_camoufox_binary
from .cli import build_config
from .config import BrowserServerConfig
from .instance_manager import InstanceManager
from .telemetry.config import read_config as _telemetry_config
from .telemetry.middleware import TelemetryMiddleware
from .telemetry.runtime import TelemetryRuntime, initialize as _initialize_telemetry
from .tools import register_all

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _run_kwargs(config: BrowserServerConfig, *, middleware: list[Middleware] | None = None) -> dict[str, Any]:
    """Build run_async kwargs from config: empty for stdio, host/port for http."""
    if config.transport == "http":
        kwargs: dict[str, Any] = {"transport": "http", "host": config.host, "port": config.port}
        if middleware:
            kwargs["middleware"] = middleware
        return kwargs
    return {}


async def main() -> None:
    """Launch the browser MCP server using the configured transport."""
    config = build_config(sys.argv[1:], os.environ)
    _setup_logging(config.log_level)
    telemetry = _initialize_telemetry(_telemetry_config(os.environ), service_version=version("justpen-browser-mcp"))
    try:
        await _serve(config, telemetry)
    except Exception:
        telemetry.events.lifecycle("mcp.server.failed", {})
        raise
    finally:
        telemetry.events.lifecycle("mcp.server.stopped", {})
        await telemetry.shutdown()


async def _prepare_browser(telemetry: TelemetryRuntime) -> BrowserRuntime:
    if not telemetry.enabled:
        return await _ensure_camoufox_binary()
    with trace.get_tracer("justpen_browser_mcp").start_as_current_span("browser.prepare", context=Context()):
        return await _ensure_camoufox_binary()


async def _cleanup_manager(mgr: InstanceManager, *, preserve_error: bool) -> None:
    failure: Exception | None = None
    for cleanup in (mgr.stop_reaper, mgr.shutdown_all):
        try:
            await cleanup()
        except Exception as error:
            logger.exception("Browser manager cleanup failed")
            if failure is None:
                failure = error
    if failure is not None and not preserve_error:
        raise failure


async def _serve(config: BrowserServerConfig, telemetry: TelemetryRuntime) -> None:

    stop_event = asyncio.Event()
    preparation_task: asyncio.Task[BrowserRuntime] | None = None

    def request_stop() -> None:
        # Repeated signals must not interrupt the worker's terminate/reap cleanup.
        if not stop_event.is_set():
            stop_event.set()
            if preparation_task is not None:
                preparation_task.cancel()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, request_stop)

    preparation_task = asyncio.create_task(_prepare_browser(telemetry), name="browser-preparation")
    try:
        runtime = await preparation_task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if stop_event.is_set() and current is not None and not current.cancelling():
            return
        raise
    finally:
        preparation_task = None
    if stop_event.is_set():
        return

    mgr = InstanceManager(config, browser_runtime=runtime)
    await _run_server(config, telemetry, mgr, stop_event)


async def _run_server(
    config: BrowserServerConfig,
    telemetry: TelemetryRuntime,
    mgr: InstanceManager,
    stop_event: asyncio.Event,
) -> None:
    if telemetry.enabled:
        mcp.add_middleware(TelemetryMiddleware(events=telemetry.events, transport=config.transport))
    register_all(mcp, mgr)
    mgr.start_reaper()
    telemetry.events.lifecycle("mcp.server.ready", {"justpen.transport": config.transport})
    # Startup or an embedding caller's context must not parent the whole server.
    token = attach(Context())
    try:
        server_task = asyncio.create_task(
            mcp.run_async(**_run_kwargs(config, middleware=telemetry.asgi_middleware())),
            name="mcp-server",
        )
    finally:
        detach(token)
    stop_task = asyncio.create_task(stop_event.wait(), name="stop-signal")

    try:
        done, _ = await asyncio.wait(
            {server_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done and not server_task.done():
            logger.info("Received shutdown signal, stopping MCP server...")
            server_task.cancel()
            # Wait for shutdown without suppressing cancellation of main itself.
            await asyncio.wait({server_task})
            if server_task.cancelled():
                return
        await server_task
    finally:
        telemetry.events.lifecycle("mcp.server.stopping", {})
        server_task.cancel()
        stop_task.cancel()
        try:
            await asyncio.gather(server_task, stop_task, return_exceptions=True)
        finally:
            await _cleanup_manager(mgr, preserve_error=sys.exception() is not None)


def cli() -> None:
    """Sync entrypoint for the `justpen-browser-mcp` console script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
