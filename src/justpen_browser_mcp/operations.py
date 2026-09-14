"""MCP execution metadata, conservative retry guidance, and bounded response payloads."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import DisabledError, FastMCPError, NotFoundError
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from pydantic import ValidationError
from typing_extensions import override

from .operation_context import Operation, current_operation
from .responses import error_response
from .telemetry.context import observe_operation

if TYPE_CHECKING:
    from fastmcp.server.middleware import CallNext, MiddlewareContext

    from .instance_manager import InstanceManager

logger = logging.getLogger(__name__)

_READ_TOOLS = frozenset(
    {
        "browser_health",
        "browser_list_instances",
        "browser_snapshot",
        "browser_frames",
        "browser_downloads",
        "browser_get_cookies",
        "browser_generate_locator",
        "browser_console_messages",
        "browser_network_requests",
        "browser_screenshot",
    }
)


def _metadata(operation: Operation, payload: dict[str, Any]) -> dict[str, Any]:
    success = payload.get("status") == "success"
    outcome = "completed" if success else "unknown" if operation.execution_started else "not_started"
    read_only = operation.tool in _READ_TOOLS or operation.tool.startswith("browser_verify_")
    retry = "not_needed" if success else "after_correction" if outcome == "not_started" else "inspect_state"
    if not success and outcome == "unknown" and read_only and not operation.artifact_write_started:
        retry = "read_only"
    data = payload.get("data", {})
    paths = [data[key] for key in ("path", "saved_to") if isinstance(data.get(key), str)]
    return {
        "id": operation.id,
        "tool": operation.tool,
        "instance_id": operation.instance_id,
        "page_id": operation.page_id,
        "frame_id": operation.frame_id,
        "started_at": operation.started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.monotonic() - operation.started_clock) * 1000, 3),
        "outcome": outcome,
        "retry": retry,
        "artifacts": [{"path": path} for path in dict.fromkeys(paths)],
    }


class OperationMiddleware(Middleware):
    """Attach request metadata while preserving the existing response envelope."""

    def __init__(self, manager: InstanceManager) -> None:
        """Bind the manager's identity lookup and configured response bound."""
        self.manager = manager

    @override
    async def on_call_tool(self, context: MiddlewareContext[Any], call_next: CallNext[Any, ToolResult]) -> ToolResult:
        """Track a tool request, resetting its context even if the client cancels."""
        arguments: dict[str, Any] = context.message.arguments or {}
        instance = arguments.get("instance", arguments.get("name"))
        target = self.manager.target_snapshot(instance) if isinstance(instance, str) else {}
        operation = Operation(
            tool=context.message.name,
            instance_id=target.get("instance_id"),
            # Explicit targets are untrusted until the manager resolves them.
            page_id=target.get("page_id") if arguments.get("page_id") is None else None,
        )
        token = current_operation.set(operation)
        observe_operation(
            operation.id,
            instance_id=operation.instance_id,
            page_id=operation.page_id,
            frame_id=operation.frame_id,
            execution_started=operation.execution_started,
        )
        deadline = asyncio.timeout(self.manager.operation_timeout_seconds)
        try:
            async with deadline:
                result = await call_next(context)
            return self._finish(operation, result)
        except TimeoutError:
            if not deadline.expired():
                raise
            result = ToolResult(
                structured_content=error_response(
                    instance if isinstance(instance, str) else None,
                    "operation_timeout",
                    "The tool exceeded the server operation deadline.",
                )
            )
            return self._finish(operation, result)
        except (FastMCPError, ValidationError, NotFoundError, DisabledError) as error:
            validation = isinstance(error, (ValidationError, NotFoundError)) or isinstance(
                error.__cause__, ValidationError
            )
            result = ToolResult(
                structured_content=error_response(
                    instance if isinstance(instance, str) else None,
                    "invalid_params" if validation else "internal_error",
                    str(error),
                ),
                is_error=True,
            )
            return self._finish(operation, result)
        except asyncio.CancelledError:
            logger.warning(
                "Operation %s (%s) cancelled; started=%s", operation.id, operation.tool, operation.execution_started
            )
            raise
        finally:
            observe_operation(
                operation.id,
                instance_id=operation.instance_id,
                page_id=operation.page_id,
                frame_id=operation.frame_id,
                execution_started=operation.execution_started,
            )
            current_operation.reset(token)

    def _finish(self, operation: Operation, result: ToolResult) -> ToolResult:
        if result.structured_content is None:
            return result
        payload = dict(result.structured_content)
        if payload.get("error_type") == "operation_timeout" and operation.action_result is not None:
            payload["data"] = {
                **operation.action_result,
                "action_completed": True,
                "observation": {"kind": operation.observation_kind, "matched": False},
            }
        metadata = _metadata(operation, payload)
        payload["operation"] = metadata
        size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        if size > self.manager.max_result_bytes:
            metadata["retry"] = "inspect_state"
            payload = {
                "status": "error",
                "instance": payload.get("instance"),
                "error_type": "result_too_large",
                "message": (
                    f"Result has {size} bytes; limit is {self.manager.max_result_bytes}. "
                    "Use a smaller scope, pagination or file output; do not blindly repeat a mutation."
                ),
                "operation": metadata,
            }
            if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > self.manager.max_result_bytes:
                # Keep identities intact: omit oversized references instead of
                # returning a shortened path or name that points somewhere else.
                payload["instance"] = None
                metadata["artifacts"] = []
                metadata["references_omitted"] = True
                # Unknown tools can contain arbitrary client-supplied names.
                if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > self.manager.max_result_bytes:
                    metadata["tool"] = None
        logger.info("Operation %s (%s) finished: %s", operation.id, operation.tool, metadata["outcome"])
        return ToolResult(structured_content=payload, meta=result.meta, is_error=result.is_error)
