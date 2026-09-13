"""Execution metadata helps clients distinguish completed work from uncertain effects."""

import asyncio
import importlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams

from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.instance_manager import InstanceManager
from justpen_browser_mcp.operation_context import Operation, current_operation, mark_operation_started
from justpen_browser_mcp.operations import OperationMiddleware
from justpen_browser_mcp.responses import error_response, success_response
from justpen_browser_mcp.tools import register_all


@pytest.mark.integration
async def test_each_mcp_operation_has_independent_identity_and_timing():
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig()))
    async with Client(server) as client:
        results = await asyncio.gather(client.call_tool("browser_health"), client.call_tool("browser_list_instances"))
    operations = [result.data["operation"] for result in results]
    assert operations[0]["id"] != operations[1]["id"]
    for operation in operations:
        UUID(operation["id"])
        assert operation["started_at"] <= operation["finished_at"]
        assert operation["duration_ms"] >= 0
        assert operation["outcome"] == "completed"
        assert operation["retry"] == "not_needed"
        assert operation["instance_id"] is None


@pytest.mark.integration
async def test_rejected_operation_reports_that_execution_did_not_start():
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig()))
    async with Client(server) as client:
        result = await client.call_tool("browser_navigate", {"instance": "missing", "url": "https://example.test"})
    assert result.data["status"] == "error"
    assert result.data["operation"]["outcome"] == "not_started"
    assert result.data["operation"]["retry"] == "after_correction"


@pytest.mark.integration
async def test_failed_started_mutation_reports_uncertainty_and_original_identity():
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig()))

    @server.tool
    async def browser_probe() -> dict[str, Any]:
        context = importlib.import_module("justpen_browser_mcp.operation_context")
        context.mark_operation_started("old-instance", page_id="actual-page")
        return error_response("example", "internal_error", "Lost acknowledgement after submitting")

    async with Client(server) as client:
        result = await client.call_tool("browser_probe")
        following = await client.call_tool("browser_health")
    operation = result.data["operation"]
    assert operation["outcome"] == "unknown"
    assert operation["retry"] == "inspect_state"
    assert operation["instance_id"] == "old-instance"
    assert operation["page_id"] == "actual-page"
    assert following.data["operation"]["instance_id"] is None


@pytest.mark.integration
async def test_oversized_result_is_explicit_error_after_completed_work():
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig(max_result_bytes=4096)))

    @server.tool
    async def browser_probe() -> dict[str, Any]:
        return success_response("example", {"result": "x" * 20_000})

    async with Client(server) as client:
        result = await client.call_tool("browser_probe")
    assert result.data["status"] == "error"
    assert result.data["error_type"] == "result_too_large"
    assert result.data["operation"]["outcome"] == "completed"
    assert result.data["operation"]["retry"] == "inspect_state"
    assert len(str(result.data)) < 4096


@pytest.mark.integration
async def test_artifact_paths_are_attached_to_the_operation(tmp_path):
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig()))

    path = str(tmp_path / "evidence.png")

    @server.tool
    async def browser_probe() -> dict[str, Any]:
        return success_response("example", {"path": path})

    async with Client(server) as client:
        result = await client.call_tool("browser_probe")
    assert result.data["operation"]["artifacts"] == [{"path": path}]


@pytest.mark.integration
async def test_oversized_references_cannot_bypass_result_limit():
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig(max_result_bytes=4096)))

    @server.tool
    async def browser_probe() -> dict[str, Any]:
        return success_response("界" * 20_000, {"path": "界" * 20_000})

    async with Client(server) as client:
        result = await client.call_tool("browser_probe")
    assert len(json.dumps(result.data, ensure_ascii=False).encode("utf-8")) <= 4096
    assert result.data["error_type"] == "result_too_large"
    assert result.data["operation"]["references_omitted"] is True
    assert result.data["operation"]["artifacts"] == []
    assert result.data["instance"] is None


@pytest.mark.integration
@pytest.mark.parametrize("arguments", [{"instance": "missing"}, {"instance": "missing", "url": [1, 2]}])
async def test_validation_errors_keep_mcp_error_and_operation_metadata(arguments):
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig()))
    async with Client(server) as client:
        result = await client.call_tool("browser_navigate", arguments, raise_on_error=False)
    assert result.is_error
    assert result.structured_content is not None
    assert result.structured_content["error_type"] == "invalid_params"
    assert result.structured_content["operation"]["outcome"] == "not_started"
    assert result.structured_content["operation"]["id"]


@pytest.mark.integration
@pytest.mark.parametrize("tool", ["browser_console_messages", "browser_network_requests", "browser_screenshot"])
async def test_artifact_write_failure_reports_uncertain_effects(manager, monkeypatch, tmp_path, tool):
    record = await manager.create("export")
    page = MagicMock()
    page.screenshot = AsyncMock(return_value=b"image")
    record.context.pages = [page]
    monkeypatch.setattr("justpen_browser_mcp.tools.inspection._PILImage", None)
    monkeypatch.setattr("anyio.Path.write_text", AsyncMock(side_effect=OSError("partial write")))
    monkeypatch.setattr("anyio.Path.write_bytes", AsyncMock(side_effect=OSError("partial write")))
    server = FastMCP("operations")
    register_all(server, manager)
    async with Client(server) as client:
        result = await client.call_tool(tool, {"instance": "export", "path": str(tmp_path / "evidence")})
    assert result.data["status"] == "error"
    assert result.data["operation"]["outcome"] == "unknown"
    assert result.data["operation"]["retry"] == "inspect_state"


def test_replaced_instance_cannot_inherit_previous_generation_page_id():
    operation = Operation(tool="browser_clear_cookies", instance_id="old", page_id="old-page")
    token = current_operation.set(operation)
    try:
        mark_operation_started("new")
        assert operation.instance_id == "new"
        assert operation.page_id is None
    finally:
        current_operation.reset(token)


@pytest.mark.integration
async def test_unknown_oversized_tool_name_is_a_bounded_tracked_mcp_error():
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig(max_result_bytes=4096)))
    async with Client(server) as client:
        result = await client.call_tool("unknown_" + "x" * 10_000, raise_on_error=False)
    assert result.is_error
    assert result.structured_content is not None
    assert len(json.dumps(result.structured_content).encode()) <= 4096
    assert result.structured_content["operation"]["outcome"] == "not_started"


@pytest.mark.integration
async def test_outer_deadline_bounds_work_outside_an_instance_lock():
    server = FastMCP("operations")
    register_all(server, InstanceManager(BrowserServerConfig(operation_timeout_seconds=0.03)))
    drained = asyncio.Event()

    @server.tool
    async def browser_probe() -> dict[str, Any]:
        mark_operation_started("probe")
        try:
            await asyncio.Event().wait()
        finally:
            drained.set()
        return success_response(None, {})

    async with Client(server) as client:
        result = await client.call_tool("browser_probe")
    assert drained.is_set()
    assert result.data["error_type"] == "operation_timeout"
    assert result.data["operation"]["outcome"] == "unknown"


async def test_external_cancellation_preserves_signal_and_resets_context():
    middleware = OperationMiddleware(InstanceManager(BrowserServerConfig()))
    context = MiddlewareContext(message=CallToolRequestParams(name="browser_probe"), method="tools/call")
    parent = Operation(tool="parent")
    token = current_operation.set(parent)

    async def cancelled(context: MiddlewareContext[Any]) -> ToolResult:
        mark_operation_started("probe")
        raise asyncio.CancelledError

    try:
        with pytest.raises(asyncio.CancelledError):
            await middleware.on_call_tool(context, cancelled)
        assert current_operation.get() is parent
    finally:
        current_operation.reset(token)


def test_frame_identity_clears_when_page_or_instance_changes():
    operation = Operation(tool="browser_snapshot")
    token = current_operation.set(operation)
    try:
        mark_operation_started("instance-a", page_id="page-a", frame_id="frame-a")
        assert operation.frame_id == "frame-a"
        mark_operation_started("instance-a", page_id="page-b")
        assert operation.frame_id is None
        mark_operation_started("instance-a", page_id="page-b", frame_id="frame-b")
        mark_operation_started("instance-b")
        assert operation.frame_id is None
        assert operation.page_id is None
    finally:
        current_operation.reset(token)


@pytest.mark.parametrize("completed", [True, False])
async def test_manager_deadline_enriches_only_completed_observed_actions(completed):
    middleware = OperationMiddleware(InstanceManager(BrowserServerConfig()))
    context = MiddlewareContext(message=CallToolRequestParams(name="browser_type"), method="tools/call")

    async def timed_out(context):
        operation = current_operation.get()
        assert operation is not None
        mark_operation_started("example")
        if completed:
            operation.action_result = {"typed_into": "e1"}
            operation.observation_kind = "response"
        return ToolResult(structured_content=error_response("example", "operation_timeout", "manager deadline"))

    result = await middleware.on_call_tool(context, timed_out)
    payload = result.structured_content
    assert payload is not None
    if completed:
        assert payload["data"] == {
            "typed_into": "e1",
            "action_completed": True,
            "observation": {"kind": "response", "matched": False},
        }
    else:
        assert "data" not in payload
    assert payload["operation"]["retry"] == "inspect_state"


@pytest.mark.parametrize("tool", ["browser_click", "custom_action"])
@pytest.mark.parametrize("result_kind", ["rejected", "timeout", "resolved"])
async def test_explicit_target_metadata_waits_for_resolution(tool, result_kind):
    manager = MagicMock()
    manager.target_snapshot.return_value = {"instance_id": "instance-1", "page_id": "active-page"}
    manager.operation_timeout_seconds = 0.01
    manager.max_result_bytes = 100000
    middleware = OperationMiddleware(manager)
    context = MiddlewareContext(
        message=CallToolRequestParams(name=tool, arguments={"instance": "example", "page_id": "requested-page"}),
        method="tools/call",
    )

    async def perform(context):
        if result_kind == "timeout":
            await asyncio.Event().wait()
        if result_kind == "resolved":
            mark_operation_started("instance-1", page_id="requested-page")
            return ToolResult(structured_content=success_response("example"))
        return ToolResult(structured_content=error_response("example", "page_not_found", "Unknown page"))

    result = await middleware.on_call_tool(context, perform)
    payload = result.structured_content
    assert payload is not None
    assert payload["operation"]["instance_id"] == "instance-1"
    assert payload["operation"]["page_id"] == ("requested-page" if result_kind == "resolved" else None)


@pytest.mark.parametrize("arguments", [{"instance": "example"}, {"instance": "example", "page_id": None}])
async def test_implicit_target_keeps_existing_active_page_metadata(arguments):
    manager = MagicMock()
    manager.target_snapshot.return_value = {"instance_id": "instance-1", "page_id": "active-page"}
    manager.operation_timeout_seconds = 1
    manager.max_result_bytes = 100000
    middleware = OperationMiddleware(manager)
    context = MiddlewareContext(
        message=CallToolRequestParams(name="browser_click", arguments=arguments), method="tools/call"
    )

    async def rejected(context):
        return ToolResult(structured_content=error_response("example", "invalid_params", "Invalid ref"))

    result = await middleware.on_call_tool(context, rejected)
    assert result.structured_content is not None
    assert result.structured_content["operation"]["page_id"] == "active-page"
