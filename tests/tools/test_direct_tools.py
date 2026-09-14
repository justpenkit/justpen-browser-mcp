"""Tool behavior with direct registered calls and isolated browser boundaries."""

import base64
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from fastmcp import FastMCP
from fastmcp.tools.function_tool import FunctionTool
from PIL import Image
from playwright.async_api import TimeoutError as PWTimeout

from justpen_browser_mcp.errors import InstanceNotFoundError, StaleRefError
from justpen_browser_mcp.instance import InstanceState
from justpen_browser_mcp.tools import code_execution, cookies, inspection, interaction, mouse, page, verification


@pytest.fixture
def direct(mock_mgr):
    server = FastMCP("direct-tool-unit")
    for module in (code_execution, cookies, inspection, interaction, mouse, page, verification):
        module.register(server, mock_mgr)

    async def invoke(tool_name, /, **arguments):
        tool = await server.get_tool(tool_name)
        assert isinstance(tool, FunctionTool)
        return await tool.fn(instance="example", **arguments)

    return invoke


@pytest.fixture
def browser(mock_mgr, monkeypatch):
    locator = MagicMock()
    for method in (
        "evaluate",
        "fill",
        "type",
        "press",
        "click",
        "dblclick",
        "hover",
        "drag_to",
        "select_option",
        "set_checked",
        "wait_for",
        "is_visible",
        "input_value",
        "is_checked",
        "aria_snapshot",
    ):
        setattr(locator, method, AsyncMock())
    locator.is_visible.return_value = True
    locator.filter.return_value.first = locator
    locator.get_by_text.return_value = locator
    browser_page = MagicMock(url="https://example.test/current")
    for method in ("evaluate", "close", "goto", "wait_for_load_state", "screenshot", "title"):
        setattr(browser_page, method, AsyncMock())
    browser_page.is_closed.return_value = False
    browser_page.locator.return_value = locator
    browser_page.keyboard.press = AsyncMock()
    for method in ("click", "move", "down", "up", "wheel"):
        setattr(browser_page.mouse, method, AsyncMock())
    browser_page.main_frame.get_by_text.return_value = locator
    browser_page.frames = [browser_page.main_frame]
    context = MagicMock(pages=[browser_page])
    for method in ("cookies", "add_cookies", "clear_cookies", "new_page"):
        setattr(context, method, AsyncMock())
    state = InstanceState(active_page=browser_page)
    mock_mgr.get.return_value = SimpleNamespace(context=context, instance_id="instance-example")
    mock_mgr.active_page.return_value = browser_page
    mock_mgr.state.return_value = state
    for module in (code_execution, interaction, verification):
        monkeypatch.setattr(module, "resolve_ref", AsyncMock(return_value=locator))
    return SimpleNamespace(page=browser_page, context=context, locator=locator, state=state)


@pytest.mark.parametrize("scope", [None, "selector", "ref"])
async def test_evaluate_scopes_expression_and_returns_its_value(direct, browser, scope):
    browser.page.evaluate.return_value = {"value": "page"}
    browser.locator.evaluate.return_value = {"value": "element"}
    arguments = {} if scope is None else {scope: "target"}
    result = await direct("browser_evaluate", expression="element => element.value", **arguments)
    expected = "page" if scope is None else "element"
    assert result["data"] == {"result": {"value": expected}}
    target = browser.page if scope is None else browser.locator
    target.evaluate.assert_awaited_once_with("element => element.value")
    if scope is not None:
        browser.page.evaluate.assert_not_awaited()


async def test_evaluate_rejects_ambiguous_scope_and_preserves_execution_failure(direct, browser):
    result = await direct("browser_evaluate", expression="1", ref="e1", selector="#target")
    assert result["error_type"] == "invalid_params"
    browser.page.evaluate.assert_not_awaited()
    browser.page.evaluate.side_effect = RuntimeError("JavaScript failed")
    result = await direct("browser_evaluate", expression="broken()")
    assert result["error_type"] == "evaluation_failed"
    assert "JavaScript failed" in result["message"]


async def test_run_code_exposes_browser_context_and_returns_traceback_on_failure(direct, browser):
    browser.page.title.return_value = "Current tab"
    result = await direct("browser_run_code", code="return [await page.title(), len(context.pages)]")
    assert result["data"] == {"result": ["Current tab", 1]}
    result = await direct("browser_run_code", code="raise ValueError('snippet failure')")
    assert result["error_type"] == "evaluation_failed"
    assert "Traceback" in result["message"]
    assert "ValueError: snippet failure" in result["message"]


@pytest.mark.parametrize(
    ("urls", "name", "expected"),
    [(None, None, ["session", "theme"]), ([], "session", ["session"]), (["https://example.test"], "missing", [])],
)
async def test_cookie_reads_forward_url_scope_and_filter_exact_names(direct, browser, urls, name, expected):
    records = [{"name": "session", "value": "secret"}, {"name": "theme", "value": "dark"}]
    browser.context.cookies.return_value = records
    result = await direct("browser_get_cookies", urls=urls, name=name)
    assert [cookie["name"] for cookie in result["data"]["cookies"]] == expected
    browser.context.cookies.assert_awaited_once_with(*(() if urls is None else (urls,)))


async def test_cookie_defaults_preserve_explicit_scope_and_caller_data(direct, browser):
    records = [
        {"name": "implicit", "value": "1"},
        {"name": "domain", "value": "2", "domain": "other.test", "path": "/account"},
        {"name": "url", "value": "3", "url": "https://url.test/path"},
    ]
    result = await direct("browser_set_cookies", cookies=records)
    assert result["data"] == {"set_count": 3}
    browser.context.add_cookies.assert_awaited_once_with(
        [
            {"name": "implicit", "value": "1", "domain": "example.test", "path": "/"},
            records[1],
            records[2],
        ]
    )
    assert records[0] == {"name": "implicit", "value": "1"}
    result = await direct("browser_clear_cookies")
    assert result["data"] == {"cleared": True}
    browser.context.clear_cookies.assert_awaited_once_with()


@pytest.mark.parametrize("has_page", [False, True])
async def test_cookie_without_origin_is_rejected_before_writing(direct, browser, has_page):
    browser.context.pages = [browser.page] if has_page else []
    browser.page.url = "about:blank"
    result = await direct("browser_set_cookies", cookies=[{"name": "session", "value": "1"}])
    assert result["error_type"] == "invalid_params"
    browser.context.add_cookies.assert_not_awaited()


@pytest.mark.parametrize(
    ("operation", "key", "value", "expected"),
    [
        ("get", None, {"__proto__": "safe"}, {"items": {"__proto__": "safe"}}),
        ("get", "missing", None, {"key": "missing", "value": None}),
        ("set", None, None, {"set_count": 1}),
        ("clear", None, None, {"cleared": True}),
    ],
)
async def test_storage_uses_temporary_page_and_preserves_response_contract(
    direct, browser, operation, key, value, expected
):
    temporary = MagicMock(
        goto=AsyncMock(), close=AsyncMock(), evaluate=AsyncMock(return_value=json.dumps({"value": value}))
    )
    browser.context.new_page.return_value = temporary
    arguments: dict[str, object] = {"origin": "https://storage.test"}
    if operation == "get":
        arguments["key"] = key
    elif operation == "set":
        arguments["items"] = {"__proto__": "safe"}
    result = await direct(f"browser_{operation}_local_storage", **arguments)
    assert result["data"] == {**expected, "origin": "https://storage.test"}
    temporary.goto.assert_awaited_once_with("https://storage.test", wait_until="commit")
    payload = temporary.evaluate.await_args.args[1]
    assert payload["operation"] == operation
    assert payload["key"] == key
    assert json.loads(payload["items"]) == arguments.get("items")
    temporary.close.assert_awaited_once_with()
    browser.page.close.assert_not_awaited()


async def test_storage_origin_mismatch_closes_temporary_page_and_active_clear_does_not_navigate(direct, browser):
    temporary = MagicMock(
        goto=AsyncMock(),
        close=AsyncMock(),
        evaluate=AsyncMock(return_value='{"mismatch": true, "origin": "https://other.test"}'),
    )
    browser.context.new_page.return_value = temporary
    result = await direct("browser_get_local_storage", origin="https://storage.test")
    assert result["error_type"] == "invalid_params"
    assert "Origin mismatch" in result["message"]
    temporary.close.assert_awaited_once_with()
    browser.context.new_page.reset_mock()
    result = await direct("browser_clear_local_storage")
    assert result["data"] == {"cleared": True, "origin": browser.page.url}
    browser.page.evaluate.assert_awaited_once_with("() => localStorage.clear()")
    browser.context.new_page.assert_not_awaited()


@pytest.mark.parametrize("selector", [None, "#main"])
async def test_snapshot_selects_page_or_scoped_capture(direct, browser, monkeypatch, selector):
    capture = AsyncMock(return_value="- button [ref=e1]")
    monkeypatch.setattr(inspection, "capture_snapshot", capture)
    browser.locator.aria_snapshot.return_value = "- heading Main"
    result = await direct("browser_snapshot", selector=selector)
    assert result["data"] == {
        "snapshot": "- button [ref=e1]" if selector is None else "- heading Main",
        "url": browser.page.url,
        "page_id": f"page-{id(browser.page)}",
        "frame_id": f"frame-{id(browser.page.main_frame)}",
    }
    if selector is None:
        capture.assert_awaited_once_with(browser.page)
        browser.locator.aria_snapshot.assert_not_awaited()
    else:
        capture.assert_not_awaited()
        browser.locator.aria_snapshot.assert_awaited_once_with(timeout=5000)


@pytest.mark.parametrize(
    ("image_format", "dimensions", "save"), [("png", (2000, 1000), False), ("jpeg", (40, 80), True)]
)
async def test_screenshot_output_matches_final_dimensions(direct, browser, tmp_path, image_format, dimensions, save):
    buffer = BytesIO()
    with Image.new("RGB", dimensions, color="red") as source:
        source.save(buffer, format=image_format.upper())
    browser.page.screenshot.return_value = buffer.getvalue()
    path = str(tmp_path / f"capture.{image_format}") if save else None
    result = await direct("browser_screenshot", image_format=image_format, full_page=True, path=path)
    data = result["data"]
    browser.page.screenshot.assert_awaited_once_with(type=image_format, full_page=True)
    expected = (1568, 784) if dimensions == (2000, 1000) else dimensions
    assert (data["width"], data["height"]) == expected
    assert (data["source_width"], data["source_height"]) == dimensions
    assert data["image_format"] == image_format
    assert data["original"] is False
    if save:
        assert "image_base64" not in data
        encoded = (tmp_path / f"capture.{image_format}").read_bytes()
    else:
        assert "path" not in data
        encoded = base64.b64decode(data["image_base64"])
    with Image.open(BytesIO(encoded)) as image:
        assert image.size == expected
        assert image.format == image_format.upper()


async def test_screenshot_rejects_format_and_keeps_bytes_when_image_processing_fails(direct, browser):
    result = await direct("browser_screenshot", image_format="gif")
    assert result["error_type"] == "invalid_params"
    browser.page.screenshot.assert_not_awaited()
    browser.page.screenshot.return_value = b"unreadable image"
    result = await direct("browser_screenshot")
    assert result["data"]["width"] is None
    assert result["data"]["height"] is None
    assert result["data"]["source_width"] is None
    assert result["data"]["source_height"] is None
    assert result["data"]["original"] is False
    assert base64.b64decode(result["data"]["image_base64"]) == b"unreadable image"


@pytest.mark.parametrize(
    ("stream", "export"), [("console", False), ("console", True), ("network", False), ("network", True)]
)
async def test_event_tools_filter_paginate_and_export_without_inline_duplication(
    direct, browser, tmp_path, stream, export
):
    if stream == "console":
        events = browser.state.console_messages
        tool, field, filters = "browser_console_messages", "messages", {"level": "error"}
        records = [
            {"type": "log", "text": "noise"},
            {"type": "error", "text": "first"},
            {"type": "error", "text": "second"},
        ]
    else:
        events = browser.state.network_requests
        tool, field, filters = "browser_network_requests", "requests", {"url_filter": "/api"}
        records = [
            {"url": "/api/image", "resource_type": "image"},
            {"url": "/api/first", "resource_type": "fetch"},
            {"url": "/api/second", "resource_type": "fetch"},
        ]
    for record in records:
        events.append(record)
    path = str(tmp_path / "events.json") if export else None
    result = await direct(tool, limit=1, path=path, **filters)
    data = result["data"]
    if export:
        assert field not in data
        assert data["count"] == 1
        first = json.loads((tmp_path / "events.json").read_text())[field]
    else:
        first = data[field]
    assert len(first) == 1
    assert all(first[0][key] == value for key, value in records[1].items())
    following = await direct(tool, after=data["next_cursor"], limit=1, **filters)
    assert all(following["data"][field][0][key] == value for key, value in records[2].items())


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("browser_console_messages", {"level": "invalid"}),
        ("browser_console_messages", {"limit": 0}),
        ("browser_network_requests", {"url_filter": "["}),
        ("browser_network_requests", {"after": "bad-cursor"}),
    ],
)
async def test_event_tools_reject_invalid_filters_and_pagination(direct, browser, tool, arguments):
    result = await direct(tool, **arguments)
    assert result["error_type"] == "invalid_params"


@pytest.mark.parametrize(("clear_first", "submit"), [(True, False), (False, True)])
async def test_type_selects_replacement_or_append_and_optional_submit(direct, browser, clear_first, submit):
    browser.page.wait_for_load_state.side_effect = PWTimeout("navigation still loading")
    result = await direct("browser_type", ref="e1", text="new value", clear_first=clear_first, submit=submit)
    assert result["data"] == {"typed_into": "e1"}
    used, unused = (
        (browser.locator.fill, browser.locator.type) if clear_first else (browser.locator.type, browser.locator.fill)
    )
    used.assert_awaited_once_with("new value")
    unused.assert_not_awaited()
    assert browser.locator.press.await_count == int(submit)
    if submit:
        browser.locator.press.assert_awaited_once_with("Enter")


@pytest.mark.parametrize("double_click", [False, True])
async def test_click_forwards_button_modifiers_and_click_mode(direct, browser, double_click):
    result = await direct("browser_click", ref="e1", button="right", modifiers=["Shift"], double_click=double_click)
    assert result["data"] == {"clicked": "e1"}
    used, unused = (
        (browser.locator.dblclick, browser.locator.click)
        if double_click
        else (browser.locator.click, browser.locator.dblclick)
    )
    used.assert_awaited_once_with(button="right", modifiers=["Shift"])
    unused.assert_not_awaited()


@pytest.mark.parametrize(
    "invalid", [{"ref": "e1"}, {"value": "missing ref"}, {"ref": "e2", "value": "x", "type": "unknown"}]
)
async def test_form_preserves_prior_updates_and_stops_at_invalid_field(direct, browser, invalid):
    result = await direct(
        "browser_fill_form", fields=[{"ref": "e1", "value": 123}, invalid, {"ref": "e3", "value": "unreached"}]
    )
    assert result["error_type"] == "invalid_params"
    browser.locator.fill.assert_awaited_once_with("123")


async def test_form_coerces_boolean_values_and_reports_completed_count(direct, browser):
    fields = [
        {"ref": "e1", "value": "false", "type": "checkbox"},
        {"ref": "e2", "value": "yes", "type": "radio"},
        {"ref": "e3", "value": 42, "type": "combobox"},
    ]
    result = await direct("browser_fill_form", fields=fields)
    assert result["data"] == {"filled_count": 3}
    assert browser.locator.set_checked.await_args_list == [call(checked=False), call(checked=True)]
    browser.locator.select_option.assert_awaited_once_with("42")


async def test_selection_hover_drag_and_enter_forward_to_resolved_targets(direct, browser):
    assert (await direct("browser_select_option", ref="e1", value=["a", "b"]))["data"] == {"selected": ["a", "b"]}
    browser.locator.select_option.assert_awaited_once_with(["a", "b"])
    assert (await direct("browser_hover", ref="e1"))["data"] == {"hovered": "e1"}
    browser.locator.hover.assert_awaited_once_with()
    assert (await direct("browser_drag", source_ref="e1", target_ref="e2"))["data"] == {"dragged": "e1", "to": "e2"}
    browser.locator.drag_to.assert_awaited_once_with(browser.locator)
    assert (await direct("browser_press_key", key="Enter"))["data"] == {"pressed": "Enter"}
    browser.page.keyboard.press.assert_awaited_once_with("Enter")
    browser.page.wait_for_load_state.assert_awaited_once_with("domcontentloaded", timeout=2000)


@pytest.mark.parametrize(
    ("tool", "arguments", "method", "args", "kwargs", "data"),
    [
        (
            "browser_mouse_click_xy",
            {"x": 10, "y": 20, "button": "right", "click_count": 2, "delay_ms": 25},
            "click",
            (10, 20),
            {"button": "right", "click_count": 2, "delay": 25},
            {"clicked_at": [10, 20], "button": "right"},
        ),
        ("browser_mouse_move_xy", {"x": 10, "y": 20}, "move", (10, 20), {}, {"moved_to": [10, 20]}),
        ("browser_mouse_down", {"button": "middle"}, "down", (), {"button": "middle"}, {"button_down": "middle"}),
        ("browser_mouse_up", {"button": "middle"}, "up", (), {"button": "middle"}, {"button_up": "middle"}),
        ("browser_mouse_wheel", {"delta_x": -10, "delta_y": 20}, "wheel", (-10, 20), {}, {"scrolled": [-10, 20]}),
    ],
)
async def test_mouse_actions_preserve_coordinates_and_options(
    direct, browser, tool, arguments, method, args, kwargs, data
):
    result = await direct(tool, **arguments)
    assert result["data"] == data
    getattr(browser.page.mouse, method).assert_awaited_once_with(*args, **kwargs)


@pytest.mark.parametrize(
    ("tool", "arguments"), [("browser_mouse_down", {"button": "extra"}), ("browser_mouse_wheel", {})]
)
async def test_invalid_mouse_input_has_no_native_effect(direct, browser, tool, arguments):
    result = await direct(tool, **arguments)
    assert result["error_type"] == "invalid_params"
    browser.page.mouse.down.assert_not_awaited()
    browser.page.mouse.wheel.assert_not_awaited()


@pytest.mark.parametrize("page_count", [0, 1, 2])
async def test_close_keeps_instance_and_selects_a_surviving_page(direct, browser, mock_mgr, page_count):
    browser.context.pages = [browser.page, MagicMock()][:page_count]
    browser.page.close.side_effect = lambda: browser.context.pages.remove(browser.page)
    result = await direct("browser_close")
    assert result["data"] == ({"closed": False, "reason": "no open pages"} if page_count == 0 else {"closed": True})
    assert browser.page.close.await_count == int(page_count > 0)
    if page_count == 2:
        mock_mgr.set_active_page.assert_called_once_with("example", 0)
    else:
        mock_mgr.set_active_page.assert_not_called()
    mock_mgr.destroy.assert_not_called()


@pytest.mark.parametrize(
    ("element_type", "actual", "expected", "success"),
    [
        ("text", "saved", "saved", True),
        ("text", "old", "new", False),
        ("checkbox", False, "false", True),
        ("radio", False, "true", False),
    ],
)
async def test_value_verification_compares_text_and_boolean_state(
    direct, browser, element_type, actual, expected, success
):
    browser.locator.input_value.return_value = actual
    browser.locator.is_checked.return_value = actual
    result = await direct("browser_verify_value", ref="e1", expected_value=expected, element_type=element_type)
    if success:
        assert result["data"] == {"ref": "e1", "value": actual, "element_type": element_type}
    else:
        assert result["error_type"] == "verification_failed"
        assert "expected" in result["message"]


@pytest.mark.parametrize("visible", [True, False])
async def test_visibility_reports_hidden_refs_and_list_items(direct, browser, visible):
    browser.locator.is_visible.return_value = visible
    cases = [
        ("browser_verify_element_visible", {"ref": "e1"}),
        ("browser_verify_list_visible", {"refs": ["e1"]}),
        ("browser_verify_list_visible", {"container_ref": "e1", "items": ["Label"]}),
    ]
    for tool, arguments in cases:
        result = await direct(tool, **arguments)
        assert result["status"] == ("success" if visible else "error")
        if not visible:
            assert result["error_type"] == "verification_failed"


@pytest.mark.parametrize(
    "arguments",
    [{}, {"refs": []}, {"container_ref": "e1"}, {"refs": ["e1"], "items": ["Label"], "container_ref": "e2"}],
)
async def test_list_verification_rejects_incomplete_or_ambiguous_modes(direct, browser, arguments):
    result = await direct("browser_verify_list_visible", **arguments)
    assert result["error_type"] == "invalid_params"
    browser.locator.is_visible.assert_not_awaited()


async def test_visibility_falls_back_to_child_frame_for_stale_main_ref(direct, browser, monkeypatch):
    monkeypatch.setattr(verification, "resolve_ref", AsyncMock(side_effect=StaleRefError("main frame ref absent")))
    child = MagicMock()
    child.locator.return_value = browser.locator
    browser.page.frames.append(child)
    result = await direct("browser_verify_element_visible", ref="e7")
    assert result["data"] == {"visible": True, "ref": "e7"}
    child.locator.assert_called_once_with("aria-ref=e7")
    browser.locator.wait_for.assert_awaited_once_with(state="attached", timeout=500)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InstanceNotFoundError("missing instance"), "instance_not_found"),
        (RuntimeError("browser disconnected"), "internal_error"),
    ],
)
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("browser_evaluate", {"expression": "1"}),
        ("browser_run_code", {"code": "return 1"}),
        ("browser_get_cookies", {}),
        ("browser_set_cookies", {"cookies": []}),
        ("browser_clear_cookies", {}),
        ("browser_get_local_storage", {"origin": "https://example.test"}),
        ("browser_set_local_storage", {"origin": "https://example.test", "items": {}}),
        ("browser_clear_local_storage", {}),
        ("browser_snapshot", {}),
        ("browser_screenshot", {}),
        ("browser_console_messages", {}),
        ("browser_network_requests", {}),
        ("browser_click", {"ref": "e1"}),
        ("browser_type", {"ref": "e1", "text": "x"}),
        ("browser_fill_form", {"fields": []}),
        ("browser_select_option", {"ref": "e1", "value": "x"}),
        ("browser_hover", {"ref": "e1"}),
        ("browser_drag", {"source_ref": "e1", "target_ref": "e2"}),
        ("browser_press_key", {"key": "Enter"}),
        ("browser_mouse_click_xy", {"x": 1, "y": 2}),
        ("browser_mouse_move_xy", {"x": 1, "y": 2}),
        ("browser_mouse_down", {}),
        ("browser_mouse_up", {}),
        ("browser_mouse_wheel", {"delta_y": 1}),
        ("browser_close", {}),
        ("browser_verify_element_visible", {"ref": "e1"}),
        ("browser_verify_list_visible", {"refs": ["e1"]}),
        ("browser_verify_value", {"ref": "e1", "expected_value": "value"}),
    ],
)
async def test_tool_failures_preserve_domain_errors_and_wrap_unexpected_failures(
    direct, mock_mgr, tool, arguments, error, expected
):
    mock_mgr.get.side_effect = error
    result = await direct(tool, **arguments)
    assert result["status"] == "error"
    assert result["instance"] == "example"
    assert result["error_type"] == expected
    assert str(error) in result["message"]


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("browser_evaluate", {"expression": "() => 1"}),
        ("browser_click", {"ref": "e1"}),
        ("browser_type", {"ref": "e1", "text": "value"}),
        ("browser_press_key", {"key": "Tab"}),
        ("browser_mouse_move_xy", {"x": 1, "y": 2}),
    ],
)
async def test_explicit_target_uses_requested_page(direct, browser, mock_mgr, tool, args):
    mock_mgr.target_page = AsyncMock(return_value=browser.page)
    result = await direct(tool, page_id="second", **args)
    assert result["status"] == "success"
    mock_mgr.target_page.assert_awaited_once_with("example", "second")
    mock_mgr.active_page.assert_not_awaited()
