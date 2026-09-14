"""Structured request events and two low-cardinality metrics on owned providers."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from opentelemetry._logs import SeverityNumber

from .payloads import known_method, safe_attributes

if TYPE_CHECKING:
    from collections.abc import Mapping

    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.util.types import AttributeValue

    from .context import RequestObservation

logger = logging.getLogger(__name__)
_LIFECYCLE_EVENTS = frozenset({"mcp.server.ready", "mcp.server.stopping", "mcp.server.stopped", "mcp.server.failed"})


class TelemetryEvents:
    """Emit fixed operational records without forwarding application logging."""

    def __init__(self, *, logger_provider: LoggerProvider | None, meter_provider: MeterProvider | None) -> None:
        """Use injected providers; a disabled signal performs no SDK work."""
        self._logger = logger_provider.get_logger("justpen_browser_mcp") if logger_provider is not None else None
        meter = meter_provider.get_meter("justpen_browser_mcp") if meter_provider is not None else None
        self._count = meter.create_counter("justpen.mcp.requests", unit="{request}") if meter is not None else None
        self._duration = meter.create_histogram("justpen.mcp.request.duration", unit="s") if meter is not None else None

    def _emit(self, event: str, attributes: Mapping[str, object]) -> None:
        if self._logger is None:
            return
        try:
            self._logger.emit(
                body=event,
                event_name=event,
                severity_number=SeverityNumber.INFO,
                attributes=safe_attributes(attributes),
            )
        except Exception:  # noqa: BLE001 — telemetry must not fail tools or disclose exception payloads
            # Never feed exporter failures back into the pipeline that failed.
            logger.warning("Telemetry event emission failed")

    def request_started(self, observation: RequestObservation) -> None:
        """Record request entry with active trace context, regardless of sampling."""
        self._emit(
            "mcp.request.started",
            {
                **observation.attributes,
                "mcp.method.name": known_method(observation.method),
                "justpen.transport": observation.transport,
            },
        )

    def request_finished(self, observation: RequestObservation) -> None:
        """Record one terminal event and duration/count without dynamic metric labels."""
        labels = {
            "mcp.method.name": known_method(observation.method),
            "justpen.transport": observation.transport,
            "justpen.result.status": observation.outcome,
        }
        attributes: dict[str, object] = {**observation.attributes, **labels}
        if observation.error_type is not None:
            attributes["error.type"] = observation.error_type
        self._emit("mcp.request.finished", attributes)
        try:
            if self._count is not None:
                self._count.add(1, labels)
            if self._duration is not None:
                self._duration.record(max(0, time.monotonic() - observation.started_clock), labels)
        except Exception:  # noqa: BLE001 — optional metrics must not change the MCP result
            logger.warning("Telemetry metric recording failed")

    def lifecycle(self, event: str, attributes: Mapping[str, AttributeValue]) -> None:
        """Emit only known lifecycle event names using the same process resource."""
        if event in _LIFECYCLE_EVENTS:
            self._emit(event, attributes)
