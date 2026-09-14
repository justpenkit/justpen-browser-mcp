"""Shared allowlists for operational telemetry; browser content is never projected."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .context import bounded_string

if TYPE_CHECKING:
    from collections.abc import Mapping

    from opentelemetry.util.types import AttributeValue

METHODS = frozenset(
    {
        "initialize",
        "ping",
        "tools/call",
        "tools/list",
        "resources/read",
        "resources/list",
        "resources/templates/list",
        "resources/subscribe",
        "resources/unsubscribe",
        "prompts/get",
        "prompts/list",
        "completion/complete",
        "logging/setLevel",
        "tasks/get",
        "tasks/result",
        "tasks/list",
        "tasks/cancel",
        "server/discover",
    }
)
ATTRIBUTE_NAMES = frozenset(
    {
        "mcp.method.name",
        "mcp.protocol.version",
        "mcp.session.id",
        "fastmcp.server.name",
        "gen_ai.tool.name",
        "gen_ai.tool.call.id",
        "justpen.client.name",
        "justpen.client.session.id",
        "justpen.client.thread.id",
        "justpen.client.turn.id",
        "justpen.client.item.id",
        "justpen.correlation.conflict",
        "justpen.request.id",
        "justpen.operation.id",
        "justpen.instance.id",
        "justpen.page.id",
        "justpen.frame.id",
        "justpen.operation.outcome",
        "justpen.operation.execution_started",
        "justpen.operation.action_completed",
        "justpen.trace.context.source",
        "justpen.trace.context.invalid",
        "justpen.trace.context.conflict",
        "justpen.transport",
        "justpen.result.status",
        "error.type",
    }
)


def known_method(value: object) -> str:
    """Bound request method cardinality, including malformed or unsupported names."""
    return value if isinstance(value, str) and value in METHODS else "unknown"


def safe_attributes(attributes: Mapping[str, object]) -> dict[str, AttributeValue]:
    """Copy selected scalar fields, omitting arbitrary payloads and oversized IDs."""
    result: dict[str, AttributeValue] = {}
    for name, value in attributes.items():
        if name not in ATTRIBUTE_NAMES:
            continue
        if name == "mcp.method.name":
            result[name] = known_method(value)
        elif isinstance(value, bool):
            result[name] = value
        elif selected := bounded_string(value):
            result[name] = selected
    return result
