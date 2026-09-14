from unittest.mock import MagicMock

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from justpen_browser_mcp.telemetry.context import extract_carrier
from justpen_browser_mcp.telemetry.export import SanitizingSpanExporter, sanitize_span
from justpen_browser_mcp.telemetry.payloads import safe_attributes


def test_export_projection_removes_content_without_breaking_trace_identity():
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource({"justpen.session.id": "pentest-a"}), shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(memory))
    parent = extract_carrier({"traceparent": f"00-{'11' * 16}-{'22' * 8}-01", "tracestate": "vendor=fixture"})
    with provider.get_tracer("fixture").start_as_current_span(
        "read sentinel-secret",
        context=parent.context,
        kind=trace.SpanKind.SERVER,
        links=[trace.Link(trace.get_current_span(parent.context).get_span_context(), {"secret": "sentinel-secret"})],
        attributes={
            "mcp.method.name": "resources/read",
            "mcp.resource.uri": "sentinel-secret",
            "arguments": "sentinel-secret",
        },
    ) as span:
        span.record_exception(ValueError("sentinel-secret"))
        span.set_status(trace.Status(trace.StatusCode.ERROR, "sentinel-secret"))
        span.add_event("sentinel-secret", {"content": "sentinel-secret"})
    raw = memory.get_finished_spans()[0]
    clean = sanitize_span(raw)
    assert "sentinel-secret" in raw.to_json()
    assert "sentinel-secret" not in clean.to_json()
    assert clean.context == raw.context
    assert clean.parent == raw.parent
    assert clean.resource == raw.resource
    assert clean.kind == raw.kind
    assert clean.start_time == raw.start_time
    assert clean.end_time == raw.end_time
    assert clean.instrumentation_scope == raw.instrumentation_scope
    assert clean.name == "resources/read"
    assert clean.status.status_code == trace.StatusCode.ERROR
    assert clean.status.description is None
    assert clean.events[0].attributes == {"exception.type": "ValueError"}
    assert clean.links[0].context == raw.links[0].context
    assert not clean.links[0].attributes
    provider.shutdown()


def test_export_failure_is_sanitized_and_not_recursive(caplog):
    delegate = MagicMock()
    delegate.export.side_effect = RuntimeError("sentinel-secret")
    exporter = SanitizingSpanExporter(delegate)
    assert exporter.export([]) == SpanExportResult.FAILURE
    assert "sentinel-secret" not in caplog.text
    assert "export" in caplog.text.lower()
    exporter.shutdown()
    delegate.shutdown.assert_called_once()


def test_successful_export_and_flush_are_delegated():
    delegate = MagicMock()
    delegate.export.return_value = SpanExportResult.SUCCESS
    delegate.force_flush.return_value = True
    exporter = SanitizingSpanExporter(delegate)
    assert exporter.export([]) == SpanExportResult.SUCCESS
    assert exporter.force_flush(123)
    delegate.force_flush.assert_called_once_with(123)


def test_unknown_tool_names_cannot_carry_client_payload():
    assert safe_attributes({"gen_ai.tool.name": "sentinel-secret"}) == {}
    assert safe_attributes({"gen_ai.tool.name": "browser_health"}) == {"gen_ai.tool.name": "browser_health"}
