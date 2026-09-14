import time
from unittest.mock import MagicMock

import pytest
from opentelemetry.context import attach, detach
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import HistogramDataPoint, InMemoryMetricReader, NumberDataPoint
from opentelemetry.sdk.resources import Resource

from justpen_browser_mcp.telemetry.context import RequestObservation, extract_carrier
from justpen_browser_mcp.telemetry.events import TelemetryEvents


@pytest.mark.parametrize("sampled", ["00", "01"])
def test_operational_logs_keep_context_and_session_without_raw_payload(sampled):
    exporter = InMemoryLogRecordExporter()
    provider = LoggerProvider(resource=Resource({"justpen.session.id": "pentest-a"}), shutdown_on_exit=False)
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    events = TelemetryEvents(logger_provider=provider, meter_provider=None)
    parent = f"00-{'11' * 16}-{'22' * 8}-{sampled}"
    token = attach(extract_carrier({"traceparent": parent}).context)
    try:
        observation = RequestObservation(
            "tools/call",
            "stdio",
            time.monotonic(),
            {
                "justpen.operation.id": "op-a",
                "arguments": "sentinel-secret",
                "exception.message": "sentinel-secret",
            },
        )
        events.request_started(observation)
        events.request_finished(observation)
        logs = exporter.get_finished_logs()
        assert len(logs) == 2
        assert [item.log_record.body for item in logs] == ["mcp.request.started", "mcp.request.finished"]
        for item in logs:
            assert item.resource.attributes["justpen.session.id"] == "pentest-a"
            assert item.log_record.trace_id == int("11" * 16, 16)
            assert item.log_record.span_id == int("22" * 8, 16)
            assert "sentinel-secret" not in repr(item.log_record.attributes)
    finally:
        detach(token)
        provider.shutdown()


def test_request_metrics_use_bounded_labels_and_seconds():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], resource=Resource({}), shutdown_on_exit=False)
    events = TelemetryEvents(logger_provider=None, meter_provider=provider)
    try:
        for outcome in ("success", "error", "cancelled"):
            events.request_finished(
                RequestObservation(
                    "tools/call",
                    "http",
                    time.monotonic() - 1.5,
                    {
                        "justpen.operation.id": "op-a",
                        "url": "https://secret.example",
                        "gen_ai.tool.name": "browser_health",
                    },
                    outcome=outcome,
                )
            )
        data = reader.get_metrics_data()
        assert data is not None
        metrics = data.resource_metrics[0].scope_metrics[0].metrics
        assert {item.name for item in metrics} == {"justpen.mcp.requests", "justpen.mcp.request.duration"}
        for metric in metrics:
            assert len(metric.data.data_points) == 3
            for point in metric.data.data_points:
                assert set(point.attributes or {}) == {"mcp.method.name", "justpen.transport", "justpen.result.status"}
                if metric.unit == "s":
                    assert isinstance(point, HistogramDataPoint)
                    assert 1.4 < point.sum < 2
                    assert point.count == 1
                else:
                    assert isinstance(point, NumberDataPoint)
                    assert point.value == 1
    finally:
        provider.shutdown()


def test_unknown_method_and_exporter_diagnostics_do_not_become_payload(caplog):
    provider = MagicMock()
    provider.get_logger.return_value.emit.side_effect = ValueError("sentinel-secret")
    events = TelemetryEvents(logger_provider=provider, meter_provider=None)
    events.request_finished(RequestObservation("sentinel-secret", "stdio", time.monotonic()))
    attrs = provider.get_logger.return_value.emit.call_args.kwargs["attributes"]
    assert attrs["mcp.method.name"] == "unknown"
    assert "sentinel-secret" not in caplog.text
    assert "telemetry" in caplog.text.lower()


def test_disabled_signals_and_lifecycle_are_safe():
    events = TelemetryEvents(logger_provider=None, meter_provider=None)
    events.request_started(RequestObservation("ping", "stdio", time.monotonic()))
    events.request_finished(RequestObservation("ping", "stdio", time.monotonic()))
    events.lifecycle("mcp.server.ready", {})
