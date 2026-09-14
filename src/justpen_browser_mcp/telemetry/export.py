"""Sanitize native FastMCP spans at the export boundary using public SDK types."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Link, Status, StatusCode
from typing_extensions import override

from .context import bounded_string
from .payloads import known_method, safe_attributes

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


def sanitize_span(span: ReadableSpan) -> ReadableSpan:
    """Keep correlation and timing while removing content, exception text and URIs."""
    attributes = safe_attributes(span.attributes or {})
    method = known_method(attributes.get("mcp.method.name"))
    name = "browser.prepare" if span.name == "browser.prepare" else method
    tool = attributes.get("gen_ai.tool.name")
    if method == "tools/call" and isinstance(tool, str):
        name = f"{method} {tool}"
    events: list[Event] = []
    for event in span.events:
        if event.name != "exception":
            continue
        error_type = bounded_string((event.attributes or {}).get("exception.type"))
        if error_type is not None:
            events.append(Event("exception", {"exception.type": error_type}, timestamp=event.timestamp))
    status = StatusCode.UNSET if attributes.get("justpen.result.status") == "cancelled" else span.status.status_code
    return ReadableSpan(
        name=name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes,
        events=events,
        links=[Link(link.context) for link in span.links],
        kind=span.kind,
        status=Status(status),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class SanitizingSpanExporter(SpanExporter):
    """Delegate only projected spans and keep failure diagnostics out of OTLP logs."""

    def __init__(self, delegate: SpanExporter) -> None:
        """Wrap an owned native OTLP exporter."""
        self.delegate = delegate

    @override
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Sanitize a batch before the delegate receives any span content."""
        try:
            result = self.delegate.export([sanitize_span(span) for span in spans])
        except Exception:  # noqa: BLE001 — export failures must not expose exception payloads or fail tools
            result = SpanExportResult.FAILURE
        if result != SpanExportResult.SUCCESS:
            logger.warning("Telemetry trace export failed; the batch may not have been delivered")
        return result

    @override
    def shutdown(self) -> None:
        """Close the owned exporter under the runtime's shutdown budget."""
        self.delegate.shutdown()

    @override
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Forward the remaining flush budget."""
        return self.delegate.force_flush(timeout_millis)


class SdkDiagnosticFilter(logging.Filter):
    """Remove SDK diagnostic payloads that can contain collector responses or headers."""

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        """Keep SDK diagnostic severity and source, never its untrusted message."""
        if record.name.startswith("opentelemetry."):
            record.msg = "Telemetry SDK diagnostic from %s"
            record.args = (record.name,)
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True
