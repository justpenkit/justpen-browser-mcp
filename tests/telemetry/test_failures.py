import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from .harness import PREFIX, Collector, WireServer
from .test_transport import PARENT, tool_spans

pytestmark = pytest.mark.integration


async def test_disabled_master_ignores_native_otel_and_writes_only_jsonrpc(tmp_path, collector):
    async with WireServer(
        tmp_path,
        collector,
        env={
            PREFIX + "ENABLED": "false",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_ENDPOINT": collector.endpoint,
        },
    ) as server:
        response = await server.call(meta={"traceparent": PARENT})
        assert response["result"]["structuredContent"]["status"] == "success"
    assert collector.records == []


@pytest.mark.parametrize("session", ["", "invalid session"])
async def test_optional_missing_session_has_no_resource_fallback(tmp_path, collector, session):
    async with WireServer(
        tmp_path,
        collector,
        env={
            "JUSTPEN_SESSION_ID": session,
            PREFIX + "RESOURCE_ATTRIBUTES": "justpen.session.id=forged,deployment.environment.name=test",
        },
    ) as server:
        await server.call(meta={"justpen.session.id": "forged", "baggage": "justpen.session.id=forged"})
    assert all("justpen.session.id" not in span["resource"] for span in collector.spans())
    assert all("justpen.session.id" not in item["resource"] for item in collector.logs())


def test_required_session_cannot_be_satisfied_by_additional_resource(tmp_path, collector):
    fixture = WireServer(
        tmp_path,
        collector,
        env={
            "JUSTPEN_SESSION_ID": "",
            PREFIX + "REQUIRE_SESSION": "true",
            PREFIX + "RESOURCE_ATTRIBUTES": "justpen.session.id=private-forged-value",
        },
    )
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("server.py"))],
        env=fixture.env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode != 0
    assert "requires a valid JUSTPEN_SESSION_ID" in result.stderr
    assert "private-forged-value" not in result.stderr
    assert result.stdout == ""
    assert collector.records == []


@pytest.mark.parametrize("selected", ["TRACES", "LOGS", "METRICS"])
async def test_signal_subsets_work_on_the_wire(tmp_path, collector, selected):
    env = {PREFIX + name + "_ENABLED": str(name == selected).lower() for name in ("TRACES", "LOGS", "METRICS")}
    async with WireServer(tmp_path, collector, env=env) as server:
        await server.call(meta={"traceparent": PARENT})
    assert collector.signals() == {selected.lower()}
    if selected == "LOGS":
        terminal = [log for log in collector.logs() if log["attributes"].get("justpen.operation.id")]
        assert terminal
        assert all(log["trace_id"] == "11" * 16 for log in terminal)


async def test_unreachable_collector_does_not_fail_requests_or_delay_exit(tmp_path, collector):
    async with WireServer(
        tmp_path,
        collector,
        transport="http",
        env={
            PREFIX + "ENDPOINT": "http://127.0.0.1:1",
            PREFIX + "SHUTDOWN_TIMEOUT_MS": "100",
        },
    ) as server:
        response = await server.call()
        assert response["result"]["structuredContent"]["status"] == "success"
        stopped = time.monotonic()
    assert time.monotonic() - stopped < 2
    assert collector.records == []


async def test_failing_collector_tiny_queues_do_not_leak_response_or_fail_tools(tmp_path):
    collector = Collector(status=503)
    try:
        async with WireServer(
            tmp_path,
            collector,
            transport="http",
            env={
                PREFIX + "BSP_MAX_QUEUE_SIZE": "2",
                PREFIX + "BLRP_MAX_QUEUE_SIZE": "2",
                PREFIX + "TIMEOUT": "0.05",
                PREFIX + "SHUTDOWN_TIMEOUT_MS": "100",
            },
        ) as server:
            responses = await asyncio.gather(*(server.call(label=str(index)) for index in range(20)))
            assert all(response["result"]["structuredContent"]["status"] == "success" for response in responses)
            stopped = time.monotonic()
        assert time.monotonic() - stopped < 2
        assert collector.records
        assert "collector-sentinel-secret" not in server.stderr_path.read_text()
    finally:
        collector.close()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
async def test_signals_flush_before_actual_http_process_exit(tmp_path, collector, sig):
    async with WireServer(tmp_path, collector, transport="http") as server:
        await server.call(meta={"traceparent": PARENT})
        assert server.process is not None
        server.process.send_signal(sig)
        started = time.monotonic()
        await asyncio.wait_for(server.process.wait(), 2)
        assert server.process.returncode == 0
    assert time.monotonic() - started < 2
    assert tool_spans(collector)
    assert any(log["body"] == "mcp.server.stopped" for log in collector.logs())


def test_blocked_exporter_has_bounded_actual_process_exit():
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("blocked_exporter.py"))],
        capture_output=True,
        text=True,
        timeout=4,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert time.monotonic() - started < 4
    assert json.loads(result.stdout)["shutdown_seconds"] < 0.6
    assert "budget expired" in result.stderr


def test_import_has_no_provider_or_worker_side_effect_even_with_enabled_env(collector):
    probe = """
import json, threading
from opentelemetry import trace
before = trace.get_tracer_provider()
from justpen_browser_mcp.telemetry import runtime
assert trace.get_tracer_provider() is before
print(json.dumps([thread.name for thread in threading.enumerate()]))
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
        env={**os.environ, PREFIX + "ENABLED": "true", PREFIX + "ENDPOINT": collector.endpoint},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["MainThread"]
    assert collector.records == []
