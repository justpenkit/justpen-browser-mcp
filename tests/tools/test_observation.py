"""Registered action observations preserve once-only effects and timeout truth."""

from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from justpen_browser_mcp.operation_context import mark_operation_started
from justpen_browser_mcp.tools import register_all


@pytest.mark.integration
@pytest.mark.parametrize("deadline", [0.01, 1])
async def test_completed_action_timeout_metadata(mock_mgr, monkeypatch, deadline):
    callbacks = defaultdict(list)
    page = MagicMock()
    page.on.side_effect = lambda event, callback: callbacks[event].append(callback)
    page.remove_listener.side_effect = lambda event, callback: callbacks[event].remove(callback)
    mock_mgr.active_page.return_value = page
    mock_mgr.operation_timeout_seconds = deadline
    mock_mgr.max_result_bytes = 100000
    mock_mgr.target_snapshot.return_value = {"instance_id": "instance-1", "page_id": "page-1"}
    filled = []

    async def fill(text):
        mark_operation_started("instance-1", page_id="page-1")
        filled.append(text)

    locator = SimpleNamespace(fill=fill)
    monkeypatch.setattr("justpen_browser_mcp.tools.interaction.resolve_ref", AsyncMock(return_value=locator))
    server = FastMCP("observed")
    register_all(server, mock_mgr)
    async with Client(server) as client:
        result = await client.call_tool(
            "browser_type",
            {
                "instance": "example",
                "ref": "e1",
                "text": "once",
                "wait_for": {"kind": "response", "url": "https://example.test/save", "timeout_ms": 20},
            },
        )
    assert result.data["error_type"] == ("operation_timeout" if deadline < 0.02 else "observation_timeout")
    assert result.data["data"]["action_completed"] is True
    assert result.data["data"]["typed_into"] == "e1"
    assert result.data["data"]["observation"]["matched"] is False
    assert result.data["operation"]["outcome"] == "unknown"
    assert result.data["operation"]["retry"] == "inspect_state"
    assert filled == ["once"]
    assert not any(callbacks.values())


@pytest.mark.integration
@pytest.mark.parametrize(
    ("tool", "arguments", "method"),
    [
        ("browser_click", {"ref": "e1"}, "click"),
        ("browser_type", {"ref": "e1", "text": "once", "submit": True}, "fill"),
        ("browser_fill_form", {"fields": [{"ref": "e1", "value": "once"}]}, "fill"),
        ("browser_select_option", {"ref": "e1", "value": "v"}, "select_option"),
        ("browser_hover", {"ref": "e1"}, "hover"),
        ("browser_drag", {"source_ref": "e1", "target_ref": "e2"}, "drag_to"),
        ("browser_press_key", {"key": "Enter"}, "press"),
        ("browser_mouse_click_xy", {"x": 1, "y": 1}, "click"),
        ("browser_mouse_drag_xy", {"from_x": 1, "from_y": 1, "to_x": 2, "to_y": 2}, "down"),
        ("browser_mouse_wheel", {"delta_y": 1}, "wheel"),
    ],
)
async def test_every_enabled_action_arms_before_effect(mock_mgr, monkeypatch, tool, arguments, method):
    callbacks = defaultdict(list)
    page = MagicMock()
    page.on.side_effect = lambda event, callback: callbacks[event].append(callback)
    page.remove_listener.side_effect = lambda event, callback: callbacks[event].remove(callback)
    page.main_frame = SimpleNamespace(page=page)
    request = SimpleNamespace(url="https://example.test/save", method="POST", frame=page.main_frame)
    effects = []

    async def effect(*args, **kwargs):
        effects.append(method)
        for callback in list(callbacks["request"]):
            callback(request)
        for callback in list(callbacks["response"]):
            callback(SimpleNamespace(request=request, url=request.url, status=500))

    locator = MagicMock()
    locator.press = AsyncMock()
    page.keyboard.press = AsyncMock()
    for name in ["move", "down", "up", "click", "wheel"]:
        setattr(page.mouse, name, AsyncMock())
    target = (
        page.mouse if tool.startswith("browser_mouse") else page.keyboard if tool == "browser_press_key" else locator
    )
    setattr(target, method, AsyncMock(side_effect=effect))
    mock_mgr.active_page.return_value = page
    mock_mgr.state.return_value.network_request_index = {}
    mock_mgr.operation_timeout_seconds = 2
    mock_mgr.max_result_bytes = 100000
    mock_mgr.target_snapshot.return_value = {}
    monkeypatch.setattr("justpen_browser_mcp.tools.interaction.resolve_ref", AsyncMock(return_value=locator))
    server = FastMCP("observed")
    register_all(server, mock_mgr)
    async with Client(server) as client:
        result = await client.call_tool(
            tool,
            {
                "instance": "example",
                **arguments,
                "wait_for": {"kind": "response", "url": request.url, "method": "post", "status": 500},
            },
        )
    assert result.data["status"] == "success"
    assert result.data["data"]["observation"]["status"] == 500
    assert result.data["data"]["action_completed"] is True
    assert effects == [method]
    page.wait_for_load_state.assert_not_called()
    assert not any(callbacks.values())


@pytest.mark.integration
async def test_action_error_does_not_claim_completion(mock_mgr, monkeypatch):
    page = MagicMock()
    mock_mgr.active_page.return_value = page
    mock_mgr.operation_timeout_seconds = 2
    mock_mgr.max_result_bytes = 100000
    mock_mgr.target_snapshot.return_value = {}
    locator = SimpleNamespace(fill=AsyncMock(side_effect=ValueError("fill failed")))
    monkeypatch.setattr("justpen_browser_mcp.tools.interaction.resolve_ref", AsyncMock(return_value=locator))
    server = FastMCP("observed")
    register_all(server, mock_mgr)
    async with Client(server) as client:
        result = await client.call_tool(
            "browser_type", {"instance": "example", "ref": "e1", "text": "once", "wait_for": {"kind": "popup"}}
        )
    assert result.data["error_type"] == "internal_error"
    assert "data" not in result.data


@pytest.mark.integration
async def test_invalid_condition_rejected_before_side_effect(mock_mgr, monkeypatch):
    mock_mgr.operation_timeout_seconds = 2
    mock_mgr.max_result_bytes = 100000
    mock_mgr.target_snapshot.return_value = {}
    locator = SimpleNamespace(fill=AsyncMock())
    monkeypatch.setattr("justpen_browser_mcp.tools.interaction.resolve_ref", AsyncMock(return_value=locator))
    server = FastMCP("observed")
    register_all(server, mock_mgr)
    async with Client(server) as client:
        result = await client.call_tool(
            "browser_type",
            {
                "instance": "example",
                "ref": "e1",
                "text": "once",
                "wait_for": {"kind": "response", "url": "u", "method": "GET POST"},
            },
            raise_on_error=False,
        )
    assert result.structured_content is not None
    assert result.structured_content["error_type"] == "invalid_params"
    assert result.structured_content["operation"]["outcome"] == "not_started"
    locator.fill.assert_not_awaited()
