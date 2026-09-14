"""Subprocess proof that a stuck exporter cannot keep the interpreter alive."""

import asyncio
import json
import threading
import time

from opentelemetry import trace
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from typing_extensions import override

from justpen_browser_mcp.telemetry import runtime
from justpen_browser_mcp.telemetry.config import read_config

entered = threading.Event()


class BlockedExporter(SpanExporter):
    @override
    def export(self, spans) -> SpanExportResult:
        entered.set()
        threading.Event().wait()
        return SpanExportResult.SUCCESS

    @override
    def shutdown(self) -> None:
        threading.Event().wait()


runtime._trace_exporter = lambda protocol: BlockedExporter()
handle = runtime.initialize(
    read_config(
        {
            "JUSTPEN_BROWSER_OTEL_ENABLED": "true",
            "JUSTPEN_BROWSER_OTEL_LOGS_ENABLED": "false",
            "JUSTPEN_BROWSER_OTEL_METRICS_ENABLED": "false",
            "JUSTPEN_BROWSER_OTEL_BSP_SCHEDULE_DELAY": "1",
            "JUSTPEN_BROWSER_OTEL_SHUTDOWN_TIMEOUT_MS": "100",
        }
    ),
    service_version="fixture",
)
with trace.get_tracer("fixture").start_as_current_span("browser.prepare"):
    pass
assert entered.wait(2)
started = time.monotonic()
asyncio.run(handle.shutdown())
print(json.dumps({"shutdown_seconds": time.monotonic() - started}))
