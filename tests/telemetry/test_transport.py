import asyncio
import json
import time
from pathlib import Path

import pytest

from justpen_browser_mcp.telemetry.payloads import KNOWN_TOOLS

from .harness import PREFIX, WireServer

pytestmark = pytest.mark.integration
PARENT = f"00-{'11' * 16}-{'22' * 8}-01"
OTHER = f"00-{'33' * 16}-{'44' * 8}-01"


def tool_spans(collector):
    return [span for span in collector.spans() if span["attributes"].get("mcp.method.name") == "tools/call"]


@pytest.mark.parametrize("transport", ["stdio", "http"])
@pytest.mark.parametrize("collector", ["http/protobuf", "grpc"], indirect=True)
async def test_remote_parent_is_preserved(tmp_path, collector, transport):
    async with WireServer(tmp_path, collector, transport=transport) as server:
        carrier = {"traceparent": PARENT, "tracestate": "vendor=fixture"}
        response = await server.call(
            meta=carrier if transport == "stdio" else None, headers=carrier if transport == "http" else None
        )
        operation_id = response["result"]["structuredContent"]["operation"]["id"]
    spans = tool_spans(collector)
    assert len(spans) == 1
    span = spans[0]
    assert span["kind"] == 2
    assert span["trace_id"] == "11" * 16
    assert span["parent_span_id"] == "22" * 8
    assert span["span_id"] != "22" * 8
    assert span["tracestate"] == "vendor=fixture"
    assert span["resource"]["justpen.session.id"] == "pentest-a"
    assert span["attributes"]["justpen.operation.id"] == operation_id
    assert span["attributes"]["justpen.trace.context.source"] == ("meta" if transport == "stdio" else "http")
    finished = [
        log
        for log in collector.logs()
        if log["body"] == "mcp.request.finished" and log["attributes"].get("justpen.operation.id") == operation_id
    ]
    assert len(finished) == 1
    assert finished[0]["trace_id"] == span["trace_id"]
    assert finished[0]["span_id"] == span["span_id"]
    assert collector.signals() == {"traces", "logs", "metrics"}
    assert all(b"sentinel-secret" not in data for _name, data, _headers in collector.records)


@pytest.mark.parametrize("stateless", [False, True])
async def test_http_precedence_fallback_and_sequential_isolation(tmp_path, collector, stateless):
    cases = [
        (None, {"traceparent": PARENT}, "meta", False, False, "11" * 16, "22" * 8),
        ({"traceparent": PARENT}, {"traceparent": OTHER}, "http", False, True, "11" * 16, "22" * 8),
        ({"traceparent": "invalid"}, {"traceparent": OTHER}, "meta", True, False, "33" * 16, "44" * 8),
        (None, {}, "new_root", False, False, None, ""),
        ({"traceparent": "invalid"}, {"traceparent": []}, "new_root", True, False, None, ""),
        (
            [("traceparent", PARENT), ("traceparent", OTHER)],
            {"traceparent": OTHER},
            "meta",
            True,
            False,
            "33" * 16,
            "44" * 8,
        ),
    ]
    expected = {}
    async with WireServer(tmp_path, collector, transport="http", stateless=stateless) as server:
        for headers, meta, source, invalid, conflict, trace_id, parent_id in cases:
            response = await server.call(meta=meta, headers=headers)
            operation = response["result"]["structuredContent"]["operation"]["id"]
            expected[operation] = (source, invalid, conflict, trace_id, parent_id)
    assert len(tool_spans(collector)) == len(cases)
    roots = []
    for span in tool_spans(collector):
        source, invalid, conflict, trace_id, parent_id = expected[span["attributes"]["justpen.operation.id"]]
        assert span["attributes"]["justpen.trace.context.source"] == source
        assert span["attributes"]["justpen.trace.context.invalid"] is invalid
        assert span["attributes"]["justpen.trace.context.conflict"] is conflict
        assert span["parent_span_id"] == parent_id
        if trace_id is None:
            roots.append(span["trace_id"])
        else:
            assert span["trace_id"] == trace_id
    assert len(set(roots)) == len(roots)


@pytest.mark.parametrize(("transport", "stateless"), [("stdio", False), ("http", False), ("http", True)])
async def test_overlapping_calls_cannot_mix_context_or_operation(tmp_path, collector, transport, stateless):
    async with WireServer(tmp_path, collector, transport=transport, stateless=stateless) as server:

        async def call(label, parent, mode):
            return await server.call(
                mode=mode,
                label=label,
                meta={"traceparent": parent, "callId": "call-" + label},
                request_id=99 if stateless else None,
            )

        first, second = await asyncio.gather(call("a", PARENT, "overlap"), call("b", OTHER, "overlap_error"))
        assert sorted(first["result"]["structuredContent"]["data"]["arrived"]) == ["a", "b"]
        assert second["result"]["structuredContent"]["status"] == "error"
    spans = tool_spans(collector)
    assert len(spans) == 2
    for span in spans:
        attrs = span["attributes"]
        label = attrs["gen_ai.tool.call.id"].removeprefix("call-")
        assert attrs["justpen.instance.id"] == "instance-" + label
        assert attrs["justpen.page.id"] == "page-" + label
        assert span["trace_id"] == ("11" if label == "a" else "33") * 16
        assert span["status"] == (0 if label == "a" else 2)
        assert attrs["justpen.result.status"] == ("success" if label == "a" else "error")
    assert len({span["attributes"]["justpen.operation.id"] for span in spans}) == 2


async def test_stateful_get_stream_does_not_parent_post_calls(tmp_path, collector):
    async with WireServer(tmp_path, collector, transport="http") as server:
        assert server.http is not None
        async with server.http.stream(
            "GET", "/mcp", headers={"Accept": "text/event-stream", "traceparent": OTHER}
        ) as stream:
            assert stream.status_code == 200
            await server.call(headers={"traceparent": PARENT})
    assert tool_spans(collector)[0]["trace_id"] == "11" * 16


@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_unsampled_parent_still_correlates_logs(tmp_path, collector, transport):
    async with WireServer(tmp_path, collector, transport=transport) as server:
        response = await server.call(meta={"traceparent": PARENT[:-2] + "00"})
        operation = response["result"]["structuredContent"]["operation"]["id"]
    assert not tool_spans(collector)
    logs = [
        log
        for log in collector.logs()
        if log["body"] == "mcp.request.finished" and log["attributes"].get("justpen.operation.id") == operation
    ]
    assert len(logs) == 1
    assert logs[0]["trace_id"] == "11" * 16
    assert logs[0]["span_id"] not in {"", "0" * 16, "22" * 8}
    assert logs[0]["resource"]["justpen.session.id"] == "pentest-a"


@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_error_envelopes_early_rejections_and_timeout_export_no_content(tmp_path, collector, transport):
    async with WireServer(
        tmp_path, collector, transport=transport, env={"BROWSER_MCP_OPERATION_TIMEOUT_SECONDS": "0.1"}
    ) as server:
        for mode in ("error", "exception", "large", "timeout"):
            response = await server.call(mode=mode, meta={"traceparent": PARENT})
            assert response["result"]["structuredContent"]["status"] == "error"
        unknown = await server.request("tools/call", {"name": "sentinel-secret"}, meta={"traceparent": PARENT})
        assert "error" in unknown or unknown["result"].get("isError")
        invalid = await server.request(
            "tools/call", {"arguments": {"secret": "sentinel-secret"}}, meta={"traceparent": PARENT}
        )
        assert "error" in invalid
    spans = tool_spans(collector)
    assert len(spans) == 6
    assert all(span["status"] == 2 for span in spans)
    assert {span["attributes"].get("error.type") for span in spans} >= {"operation_timeout", "result_too_large"}
    timeout = next(span for span in spans if span["attributes"].get("error.type") == "operation_timeout")
    assert timeout["attributes"]["justpen.operation.action_completed"] is True
    assert (
        len(
            [
                log
                for log in collector.logs()
                if log["body"] == "mcp.request.finished" and log["attributes"].get("mcp.method.name") == "tools/call"
            ]
        )
        == 6
    )
    assert all(b"sentinel-secret" not in data for _name, data, _headers in collector.records)


@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_cancellation_retains_operation_and_next_call_is_clean(tmp_path, collector, transport):
    async with WireServer(tmp_path, collector, transport=transport) as server:
        task = asyncio.create_task(
            server.call(mode="block", label="cancel", meta={"traceparent": PARENT}, request_id=777)
        )
        try:
            operation = await server.wait_for_running("cancel")
            await server.notify("notifications/cancelled", {"requestId": 777, "reason": "sentinel-secret"})
            deadline = time.monotonic() + 3
            terminal = []
            while time.monotonic() < deadline:
                terminal = [
                    log
                    for log in collector.logs()
                    if log["body"] == "mcp.request.finished"
                    and log["attributes"].get("justpen.operation.id") == operation
                ]
                if terminal:
                    break
                await asyncio.sleep(0.02)
            assert len(terminal) == 1
            assert terminal[0]["attributes"]["justpen.result.status"] == "cancelled"
            await server.request("tools/call", {"name": "browser_health"}, meta={"traceparent": OTHER})
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    cancelled = next(
        span for span in tool_spans(collector) if span["attributes"].get("justpen.operation.id") == operation
    )
    assert cancelled["status"] == 0
    healthy = next(
        span for span in tool_spans(collector) if span["attributes"].get("gen_ai.tool.name") == "browser_health"
    )
    assert healthy["trace_id"] == "33" * 16
    assert "justpen.instance.id" not in healthy["attributes"]


@pytest.mark.parametrize(
    ("name", "meta", "call_id"),
    [
        (
            "codex-mcp-client",
            {
                "callId": "call_original",
                "threadId": "thread-a",
                "itemId": "item-a",
                "x-codex-turn-metadata": {"session_id": "native-session", "thread_id": "thread-a", "turn_id": "turn-a"},
            },
            "call_original",
        ),
        ("claude-code", {"claudecode/toolUseId": "toolu_original"}, "toolu_original"),
    ],
)
async def test_native_client_identifiers_are_not_pentest_identity(tmp_path, collector, name, meta, call_id):
    async with WireServer(tmp_path, collector, client_name=name) as server:
        await server.call(meta=meta)
    span = tool_spans(collector)[0]
    assert span["attributes"]["gen_ai.tool.call.id"] == call_id
    assert span["attributes"]["justpen.client.name"] == name
    assert span["resource"]["justpen.session.id"] == "pentest-a"
    assert span["attributes"].get("justpen.client.session.id") == (
        "native-session" if name == "codex-mcp-client" else None
    )


@pytest.mark.parametrize("collector", ["http/protobuf", "grpc"], indirect=True)
async def test_sdk_environment_isolated_and_exporter_endpoint_header_precedence(tmp_path, collector):
    env = {
        "OTEL_SDK_DISABLED": "true",
        "OTEL_RESOURCE_ATTRIBUTES": "justpen.session.id=wrong,leaked=sentinel-secret",
        "OTEL_SERVICE_NAME": "wrong",
        "OTEL_TRACES_SAMPLER": "always_off",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:1",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        "OTEL_EXPORTER_OTLP_HEADERS": "authorization=ambient-secret",
        PREFIX + "HEADERS": "authorization=browser-secret",
        PREFIX + "TRACES_HEADERS": "authorization=trace-secret",
        PREFIX + "TRACES_ENDPOINT": collector.endpoint
        + ("/custom/traces" if collector.protocol == "http/protobuf" else ""),
        PREFIX
        + "RESOURCE_ATTRIBUTES": "deployment.environment.name=test,justpen.session.id=wrong,justpen%2Esession%2Eid=wrong",
    }
    async with WireServer(tmp_path, collector, env=env) as server:
        await server.call(meta={"traceparent": PARENT})
    assert tool_spans(collector)[0]["trace_id"] == "11" * 16
    for span in collector.spans():
        assert span["resource"]["justpen.session.id"] == "pentest-a"
        assert span["resource"]["service.name"] == "justpen-browser-mcp"
        assert span["resource"]["deployment.environment.name"] == "test"
        assert "leaked" not in span["resource"]
    for name, data, headers in collector.records:
        received = {key.lower(): value for key, value in headers.items()}
        assert received["authorization"] == ("trace-secret" if name == "traces" else "browser-secret")
        assert b"secret" not in data
    assert collector.signals() == {"traces", "logs", "metrics"}
    if collector.protocol == "http/protobuf":
        assert set(collector.paths) == {"/custom/traces", "/v1/logs", "/v1/metrics"}


async def test_process_resources_keep_session_across_runs_without_cross_pentest_leaks(tmp_path, collector):
    expected = [("pentest-a", "run-1"), ("pentest-a", "run-2"), ("pentest-b", "run-3")]
    for session, run in expected:
        async with WireServer(
            tmp_path,
            collector,
            env={
                "JUSTPEN_SESSION_ID": session,
                PREFIX + "RESOURCE_ATTRIBUTES": "justpen.run.id=" + run,
            },
        ) as server:
            await server.call()
    spans = tool_spans(collector)
    assert {(span["resource"]["justpen.session.id"], span["resource"]["justpen.run.id"]) for span in spans} == set(
        expected
    )
    assert len({span["resource"]["service.instance.id"] for span in spans}) == 3
    assert len({span["trace_id"] for span in spans}) == 3


async def test_tool_schemas_unchanged_and_metrics_have_no_request_identity(tmp_path, collector):
    async with WireServer(tmp_path, collector) as server:
        response = await server.request("tools/list", {})
        schemas = {
            tool["name"]: tool["inputSchema"]
            for tool in response["result"]["tools"]
            if not tool["name"].startswith("browser_telemetry_")
        }
        expected = json.loads((Path(__file__).parents[1] / "fixtures/tool-input-schemas.json").read_text())
        assert schemas == expected
        assert len(schemas) == 46
        assert set(schemas) == KNOWN_TOOLS
        await server.call()
    assert collector.metrics()
    for payload in collector.metrics():
        for resource in payload["resource_metrics"]:
            for scope in resource["scope_metrics"]:
                for metric in scope["metrics"]:
                    assert metric["name"] in {"justpen.mcp.requests", "justpen.mcp.request.duration"}
                    points = metric.get("sum", metric.get("histogram", {}))["data_points"]
                    for point in points:
                        assert {item["key"] for item in point["attributes"]} == {
                            "mcp.method.name",
                            "justpen.transport",
                            "justpen.result.status",
                        }


async def test_oversized_metadata_is_rejected_before_native_span_creation(tmp_path, collector):
    async with WireServer(tmp_path, collector) as server:
        await server.call(meta={"traceparent": "01" + PARENT[2:] + "-" + "x" * 600})
    span = tool_spans(collector)[0]
    assert span["parent_span_id"] == ""
    assert span["attributes"]["justpen.trace.context.source"] == "new_root"
    assert span["attributes"]["justpen.trace.context.invalid"] is True
