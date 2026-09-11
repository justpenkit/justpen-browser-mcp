"""Request-local execution identity shared by the manager and MCP middleware."""

from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Operation:
    """Track one request without sharing mutable state across concurrent calls."""

    tool: str
    instance_id: str | None = None
    page_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_clock: float = field(default_factory=time.monotonic)
    execution_started: bool = False
    artifact_write_started: bool = False


current_operation: ContextVar[Operation | None] = ContextVar("browser_operation", default=None)


def mark_operation_started(instance_id: str | None, *, page_id: str | None = None) -> None:
    """Record that execution acquired its target, without inventing side-effect certainty."""
    operation = current_operation.get()
    if operation is not None:
        operation.execution_started = True
        if instance_id is not None:
            if instance_id != operation.instance_id:
                operation.page_id = None
            operation.instance_id = instance_id
        if page_id is not None:
            operation.page_id = page_id


def mark_artifact_write_started() -> None:
    """Record that a server file may have been created or partially overwritten."""
    operation = current_operation.get()
    if operation is not None:
        operation.execution_started = True
        operation.artifact_write_started = True
