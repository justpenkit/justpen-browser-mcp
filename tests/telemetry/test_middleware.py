import asyncio
import copy
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from justpen_browser_mcp.telemetry.context import (
    RequestObservation,
    current_observation,
    extract_carrier,
    incoming_http,
    observe_operation,
)
from justpen_browser_mcp.telemetry.middleware import TelemetryMiddleware
from justpen_browser_mcp.telemetry.payloads import apply_tool_result


@pytest.mark.parametrize(
    ("payload", "is_error", "outcome", "error_type"),
    [
        ({"status": "success"}, False, "success", None),
        (
            {"status": "error", "error_type": "operation_timeout", "message": "sentinel-secret"},
            False,
            "error",
            "operation_timeout",
        ),
        ({"status": "success"}, True, "error", "tool_error"),
        ({"status": "error", "error_type": "sentinel-secret"}, False, "error", "tool_error"),
    ],
)
def test_final_tool_envelope_is_authoritative_and_not_mutated(payload, is_error, outcome, error_type):
    result = ToolResult(structured_content=payload, is_error=is_error)
    before = copy.deepcopy(result.structured_content)
    observation = RequestObservation("tools/call", "stdio", time.monotonic())
    apply_tool_result(observation, result)
    assert observation.outcome == outcome
    assert observation.error_type == error_type
    assert "sentinel-secret" not in repr(observation)
    assert result.structured_content == before


@pytest.mark.parametrize("failure", [None, ValueError, asyncio.CancelledError])
async def test_one_terminal_event_uses_native_span_and_resets_context(failure):
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource({}), shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(memory))
    events = MagicMock()
    middleware = TelemetryMiddleware(events=events, transport="stdio")
    ctx = MiddlewareContext(method="tools/call", message=CallToolRequestParams(name="browser_health"))

    async def call_next(context):
        observe_operation("op-a", instance_id="instance-a", page_id="page-a", frame_id=None, execution_started=True)
        if failure:
            raise failure("sentinel-secret")
        return ToolResult(structured_content={"status": "error", "error_type": "result_too_large"})

    with provider.get_tracer("native-fixture").start_as_current_span(
        "tools/call", record_exception=False, set_status_on_exception=False
    ):
        if failure:
            with pytest.raises(failure):
                await middleware(ctx, call_next)
        else:
            await middleware(ctx, call_next)
    events.request_started.assert_called_once()
    events.request_finished.assert_called_once()
    observation = events.request_finished.call_args.args[0]
    assert observation.attributes["justpen.operation.id"] == "op-a"
    assert observation.outcome == ("cancelled" if failure is asyncio.CancelledError else "error")
    assert current_observation.get() is None
    spans = memory.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code == (StatusCode.UNSET if failure is asyncio.CancelledError else StatusCode.ERROR)
    assert "sentinel-secret" not in repr(spans[0].attributes)
    provider.shutdown()


async def test_http_source_wins_and_client_metadata_uses_public_context():
    meta = {"traceparent": f"00-{'33' * 16}-{'44' * 8}-01", "callId": "call-a", "justpen.session.id": "untrusted"}
    fastmcp_context = MagicMock()
    fastmcp_context.request_context.meta = meta
    fastmcp_context.request_context.request_id = 42
    fastmcp_context.session.client_params.client_info.name = "codex-mcp-client"
    events = MagicMock()
    token = incoming_http.set(extract_carrier({"traceparent": f"00-{'11' * 16}-{'22' * 8}-01"}))
    try:
        await TelemetryMiddleware(events=events, transport="http")(
            MiddlewareContext(method="ping", message={}, fastmcp_context=fastmcp_context), AsyncMock(return_value={})
        )
    finally:
        incoming_http.reset(token)
    attrs = events.request_finished.call_args.args[0].attributes
    assert attrs["justpen.trace.context.source"] == "http"
    assert attrs["justpen.trace.context.conflict"] is True
    assert attrs["justpen.request.id"] == "42"
    assert attrs["gen_ai.tool.call.id"] == "call-a"
    assert attrs["justpen.client.name"] == "codex-mcp-client"
    assert "justpen.session.id" not in attrs


def test_resolved_operation_target_can_clear_an_obsolete_page():
    observation = RequestObservation("tools/call", "stdio", time.monotonic())
    token = current_observation.set(observation)
    try:
        observe_operation("op-a", instance_id="first", page_id="page-a", frame_id="frame-a", execution_started=False)
        observe_operation("op-a", instance_id="second", page_id=None, frame_id=None, execution_started=True)
    finally:
        current_observation.reset(token)
    assert observation.attributes["justpen.instance.id"] == "second"
    assert "justpen.page.id" not in observation.attributes
    assert "justpen.frame.id" not in observation.attributes
