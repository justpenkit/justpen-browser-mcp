"""Regression tests for tool state, browser semantics, and recovery."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import anyio
import anyio.lowlevel
import pytest
from playwright.async_api import Error as PlaywrightError, TimeoutError as PWTimeout

from justpen_browser_mcp.errors import InvalidParamsError
from justpen_browser_mcp.instance import InstanceState
from justpen_browser_mcp.operation_context import Operation, current_operation
from justpen_browser_mcp.ref_resolver import _internal_to_python
from justpen_browser_mcp.tools import (
    code_execution,
    cookies,
    interaction,
    mouse,
    navigation,
    page,
    utility,
    verification,
)


class Registry:
    def __init__(self):
        self.functions = {}

    def tool(self, function):
        self.functions[function.__name__] = function
        return function


@pytest.fixture
def tools(mock_mgr):
    registry = Registry()
    for module in (navigation, cookies, interaction, mouse, utility, code_execution, page, verification):
        module.register(registry, mock_mgr)
    return registry.functions


@pytest.fixture
def active(mock_mgr):
    browser_page = MagicMock()
    browser_page.url = "https://example.test/"
    browser_page.is_closed.return_value = False
    for method in ("goto", "title", "wait_for_load_state", "close", "bring_to_front", "evaluate"):
        setattr(browser_page, method, AsyncMock())
    browser_page.title.return_value = "Example"
    ctx = MagicMock(pages=[browser_page])
    mock_mgr.get.return_value = SimpleNamespace(context=ctx, instance_id="instance-test")
    mock_mgr.active_page.return_value = browser_page
    state = InstanceState(active_page=browser_page)
    mock_mgr.state.return_value = state
    mock_mgr.page_id.side_effect = lambda _name, target: f"page-{id(target)}"

    def select(_name, index):
        state.active_page_index = index
        state.active_page = ctx.pages[index]

    mock_mgr.set_active_page.side_effect = select
    return browser_page, ctx, state


@pytest.mark.parametrize("suffix", ["download", "ordinary"])
async def test_navigation_failure_needs_actual_download(tools, active, suffix):
    browser_page, _, _ = active
    url = f"https://example.test/{suffix}"
    browser_page.goto.side_effect = PlaywrightError(f"NS_ERROR_CONNECTION_REFUSED navigating to {url}")
    result = await tools["browser_navigate"]("test", url)
    assert result["error_type"] == "navigation_failed"


@pytest.mark.parametrize("download_url", ["https://example.test/file", "https://elsewhere.test/background"])
async def test_download_must_correlate_with_navigation(tools, active, download_url):
    browser_page, _, _ = active
    listeners = {}
    browser_page.on.side_effect = lambda event, callback: listeners.update({event: callback})

    async def navigate(url, **_kwargs):
        request = MagicMock(url=url, frame=browser_page.main_frame, redirected_from=None)
        request.is_navigation_request.return_value = True
        if "request" in listeners:
            listeners["request"](request)
        if "download" in listeners:
            listeners["download"](MagicMock(url=download_url))
        raise PlaywrightError("NS_BINDING_ABORTED")

    browser_page.goto.side_effect = navigate
    result = await tools["browser_navigate"]("test", "https://example.test/file")
    if download_url.endswith("/file"):
        assert result["data"]["download"] is True
    else:
        assert result["error_type"] == "navigation_failed"
    assert browser_page.remove_listener.call_count == 2


@pytest.mark.parametrize("url", ["data:text/html,<h1>a.b</h1>", "javascript:document.title", "about:blank"])
def test_explicit_url_schemes_are_preserved(url):
    assert navigation.canonicalize_browser_url(url) == url


def test_schemeless_hostname_port_keeps_https_inference():
    assert navigation.canonicalize_browser_url("example.test:8443/path") == "https://example.test:8443/path"


@pytest.mark.parametrize("condition", ["text", "text_gone"])
async def test_wait_uses_visible_matches_instead_of_hidden_first(tools, active, condition):
    browser_page, _, _ = active
    all_matches = MagicMock()
    all_matches.first.wait_for = AsyncMock(side_effect=PWTimeout("hidden first") if condition == "text" else None)
    visible_matches = MagicMock()
    visible_matches.first.wait_for = AsyncMock(
        side_effect=PWTimeout("still visible") if condition == "text_gone" else None
    )
    all_matches.filter.return_value = visible_matches
    browser_page.get_by_text.return_value = all_matches
    result = await tools["browser_wait_for"]("test", **{condition: "Done"})
    assert result["status"] == ("success" if condition == "text" else "error")
    all_matches.filter.assert_called_with(visible=True)


@pytest.mark.parametrize("container", [False, True])
async def test_verification_accepts_visible_duplicate(tools, active, container):
    browser_page, _, _ = active
    matches = MagicMock()
    matches.first.is_visible = AsyncMock(return_value=False)
    matches.filter.return_value.first.is_visible = AsyncMock(return_value=True)
    if container:
        locator = MagicMock(wait_for=AsyncMock())
        locator.get_by_text.return_value = matches
        browser_page.locator.return_value = locator
        result = await tools["browser_verify_list_visible"]("test", container_ref="e1", items=["Done"])
    else:
        browser_page.main_frame.get_by_text.return_value = matches
        browser_page.frames = [browser_page.main_frame]
        result = await tools["browser_verify_text_visible"]("test", "Done")
    assert result["status"] == "success"


@pytest.mark.parametrize(
    "selector",
    [
        'internal:role=button[name="Same"i] >> nth=1',
        'internal:role=checkbox[checked=true][name="Agree"i]',
        'internal:role=region[name="A"i] >> internal:role=button[name="Run"i]',
        'iframe >> internal:control=enter-frame >> internal:role=button[name="Same"i] >> nth=1',
    ],
)
def test_complex_selector_python_form_is_lossless(selector):
    assert _internal_to_python(selector) == f"locator({selector!r})"


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("browser_navigate", {"url": "about:blank"}),
        ("browser_navigate_back", {}),
        ("browser_wait_for", {"time": 0}),
        ("browser_resize", {"width": 800, "height": 600}),
        ("browser_generate_locator", {"selector": "button"}),
        ("browser_click", {"ref": "e1"}),
        ("browser_mouse_click_xy", {"x": 0, "y": 0}),
        ("browser_mouse_drag_xy", {"from_x": 0, "from_y": 0, "to_x": 1, "to_y": 1}),
    ],
)
async def test_modal_guard_checks_state_after_acquiring_lock(tools, active, mock_mgr, tool_name, arguments):
    browser_page, _, state = active

    @asynccontextmanager
    async def acquire(_instance):
        state.modal_states.append(
            {
                "kind": "dialog",
                "page": browser_page,
                "object": SimpleNamespace(type="alert", message="opened while waiting"),
            }
        )
        yield

    mock_mgr.lock_for.side_effect = acquire
    mock_mgr.get_modal_states.side_effect = lambda _instance: state.modal_states
    result = await tools[tool_name]("test", **arguments)
    assert result["error_type"] == "modal_state_blocked"


async def test_new_tab_selects_created_page_when_popup_is_last(tools, active, mock_mgr):
    original, ctx, state = active
    opened = MagicMock(url="https://example.test/requested", is_closed=MagicMock(return_value=False))
    popup = MagicMock(url="https://example.test/popup")

    async def new_page():
        ctx.pages.append(opened)
        return opened

    async def navigate(_url):
        ctx.pages.append(popup)

    ctx.new_page = new_page
    opened.goto = navigate
    result = await tools["browser_tabs"]("test", "new", url=opened.url)
    assert ctx.pages == [original, opened, popup]
    assert state.active_page is opened
    assert result["data"] == {"index": 1, "url": opened.url, "page_id": mock_mgr.page_id("test", opened)}


async def test_failed_new_tab_is_closed_and_selection_preserved(tools, active):
    original, ctx, state = active
    opened = MagicMock(goto=AsyncMock(side_effect=PlaywrightError("failed")))

    async def close():
        ctx.pages.remove(opened)

    async def new_page():
        ctx.pages.append(opened)
        return opened

    opened.close = AsyncMock(side_effect=close)
    ctx.new_page = new_page
    result = await tools["browser_tabs"]("test", "new", url="https://example.test/fail")
    assert result["status"] == "error"
    assert ctx.pages == [original]
    assert state.active_page is original


async def test_cancelled_new_tab_cleanup_survives_cancel_scope(tools, active):
    original, ctx, _ = active
    opened = MagicMock()

    async def close():
        await anyio.lowlevel.checkpoint()
        ctx.pages.remove(opened)

    async def new_page():
        ctx.pages.append(opened)
        return opened

    with anyio.CancelScope() as scope:

        async def navigate(_url):
            scope.cancel()
            await anyio.lowlevel.checkpoint()

        opened.goto = navigate
        opened.close = close
        ctx.new_page = new_page
        await tools["browser_tabs"]("test", "new", url="https://example.test/cancelled")
    assert ctx.pages == [original]


@pytest.mark.parametrize("action", ["select", "close"])
async def test_tab_id_survives_index_shift(tools, active, mock_mgr, action):
    _, ctx, state = active
    target = MagicMock(url="https://target.test", bring_to_front=AsyncMock())
    ctx.pages.append(target)
    page_id = mock_mgr.page_id("test", target)
    ctx.pages.pop(0)

    async def close():
        ctx.pages.remove(target)

    target.close = AsyncMock(side_effect=close)
    result = await tools["browser_tabs"]("test", action, page_id=page_id)
    assert result["status"] == "success"
    assert result["data"]["page_id"] == page_id
    if action == "select":
        assert state.active_page is target
    else:
        assert ctx.pages == []


async def test_tab_id_and_index_are_mutually_exclusive(tools, active):
    result = await tools["browser_tabs"]("test", "select", index=0, page_id="page-one")
    assert result["error_type"] == "invalid_params"


async def test_pdf_reports_unsupported_capability_without_attempting_render(tools, active, tmp_path):
    browser_page, _, _ = active
    target = tmp_path / "evidence.pdf"
    result = await tools["browser_pdf_save"]("test", str(target))
    assert result["error_type"] == "unsupported_capability"
    browser_page.pdf.assert_not_called()
    assert not target.exists()


@pytest.mark.parametrize("failure", [ValueError("move failed"), asyncio.CancelledError()])
async def test_drag_releases_mouse_after_error_or_cancellation(tools, active, failure):
    browser_page, _, _ = active
    browser_page.mouse.down = AsyncMock()
    browser_page.mouse.up = AsyncMock()
    browser_page.mouse.move = AsyncMock(side_effect=[None, failure])
    if isinstance(failure, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await tools["browser_mouse_drag_xy"]("test", 0, 0, 10, 10)
    else:
        result = await tools["browser_mouse_drag_xy"]("test", 0, 0, 10, 10)
        assert "move failed" in result["message"]
    browser_page.mouse.up.assert_awaited_once()


async def test_cancelled_mouse_down_still_releases_button(tools, active):
    browser_page, _, _ = active
    browser_page.mouse.move = AsyncMock()
    browser_page.mouse.down = AsyncMock(side_effect=asyncio.CancelledError())
    browser_page.mouse.up = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        await tools["browser_mouse_drag_xy"]("test", 0, 0, 1, 1)
    browser_page.mouse.up.assert_awaited_once()


async def test_drag_preserves_move_error_if_cleanup_fails(tools, active):
    browser_page, _, _ = active
    browser_page.mouse.down = AsyncMock()
    browser_page.mouse.move = AsyncMock(side_effect=[None, ValueError("original move error")])
    browser_page.mouse.up = AsyncMock(side_effect=ValueError("cleanup error"))
    result = await tools["browser_mouse_drag_xy"]("test", 0, 0, 1, 1)
    assert "original move error" in result["message"]


@pytest.mark.parametrize(
    ("kind", "tool_name", "arguments"),
    [
        ("dialog", "browser_handle_dialog", {"accept": False}),
        ("filechooser", "browser_file_upload", {"paths": ["file.txt"]}),
    ],
)
@pytest.mark.parametrize("cancelled", [False, True])
async def test_modal_recovery_retains_state_when_resolution_fails(
    tools, active, mock_mgr, kind, tool_name, arguments, cancelled
):
    browser_page, _, state = active
    failure = asyncio.CancelledError() if cancelled else PlaywrightError("resolution failed")
    modal = MagicMock(dismiss=AsyncMock(side_effect=failure), set_files=AsyncMock(side_effect=failure))
    entry = {"kind": kind, "object": modal, "page": browser_page}
    state.modal_states.append(entry)
    mock_mgr.get_modal_states.side_effect = lambda _name: list(state.modal_states)
    mock_mgr.consume_modal_state.side_effect = lambda *_args, **_kwargs: state.modal_states.pop(0)
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await tools[tool_name]("test", **arguments)
    else:
        result = await tools[tool_name]("test", **arguments)
        assert result["status"] == "error"
    assert state.modal_states == [entry]
    mock_mgr.modal_lock_for.assert_called_once_with("test")
    mock_mgr.lock_for.assert_not_called()


@pytest.mark.parametrize("action", ["new", "select", "close"])
async def test_tab_operation_metadata_identifies_actual_target(tools, active, mock_mgr, action):
    original, ctx, _ = active
    target = MagicMock(url="about:blank", bring_to_front=AsyncMock(), close=AsyncMock())
    if action == "new":

        async def new_page():
            ctx.pages.append(target)
            return target

        ctx.new_page = new_page
        arguments = {}
    else:
        ctx.pages.append(target)
        arguments = {"index": 1}
    operation = Operation("browser_tabs", instance_id="instance-test", page_id=mock_mgr.page_id("test", original))
    token = current_operation.set(operation)
    try:
        result = await tools["browser_tabs"]("test", action, **arguments)
    finally:
        current_operation.reset(token)
    assert result["status"] == "success", result
    assert operation.page_id == mock_mgr.page_id("test", target)


@pytest.mark.parametrize("kind", ["dialog", "filechooser"])
async def test_modal_operation_metadata_identifies_nonactive_popup(tools, active, mock_mgr, kind):
    original, ctx, _ = active
    popup = MagicMock(is_closed=MagicMock(return_value=False), wait_for_load_state=AsyncMock())
    ctx.pages.append(popup)
    modal = MagicMock(dismiss=AsyncMock(), set_files=AsyncMock())
    mock_mgr.consume_modal_state.return_value = {"kind": kind, "object": modal, "page": popup}
    operation = Operation("recovery", instance_id="instance-test", page_id=mock_mgr.page_id("test", original))
    token = current_operation.set(operation)
    try:
        if kind == "dialog":
            result = await tools["browser_handle_dialog"]("test", accept=False)
        else:
            result = await tools["browser_file_upload"]("test", paths=["file.txt"])
    finally:
        current_operation.reset(token)
    assert result["status"] == "success", result
    assert operation.page_id == mock_mgr.page_id("test", popup)


@pytest.mark.parametrize("kind", ["dialog", "filechooser"])
async def test_closed_modal_page_is_reported_before_resolving_its_id(tools, active, mock_mgr, kind):
    popup = MagicMock(is_closed=MagicMock(return_value=True))
    modal = MagicMock(dismiss=AsyncMock(), set_files=AsyncMock())
    mock_mgr.consume_modal_state.return_value = {"kind": kind, "object": modal, "page": popup}
    mock_mgr.page_id.side_effect = InvalidParamsError("Page is closed or is not owned by this instance.")
    if kind == "dialog":
        result = await tools["browser_handle_dialog"]("test", accept=False)
    else:
        result = await tools["browser_file_upload"]("test", paths=["file.txt"])
    assert result["error_type"] == "modal_state_blocked"
    assert "closed" in result["message"]
    mock_mgr.page_id.assert_not_called()


async def test_drag_cancellation_during_release_overrides_earlier_move_error(tools, active):
    browser_page, _, _ = active
    releasing = asyncio.Event()
    release = asyncio.Event()

    async def mouse_up():
        releasing.set()
        await release.wait()

    browser_page.mouse.down = AsyncMock()
    browser_page.mouse.move = AsyncMock(side_effect=[None, ValueError("move failed")])
    browser_page.mouse.up = AsyncMock(side_effect=mouse_up)
    task = asyncio.create_task(tools["browser_mouse_drag_xy"]("test", 0, 0, 1, 1))
    await asyncio.wait_for(releasing.wait(), timeout=1)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    browser_page.mouse.up.assert_awaited_once()


@pytest.mark.parametrize("accept", [True, False])
async def test_already_handled_dialog_is_discarded(tools, active, mock_mgr, accept):
    browser_page, _, state = active
    error = PlaywrightError("Dialog.dismiss: Cannot accept dialog which is already handled!")
    modal = MagicMock(accept=AsyncMock(side_effect=error), dismiss=AsyncMock(side_effect=error))
    entry = {"kind": "dialog", "object": modal, "page": browser_page}
    state.modal_states.append(entry)
    mock_mgr.consume_modal_state.side_effect = lambda *_args, **_kwargs: state.modal_states.pop(0)
    result = await tools["browser_handle_dialog"]("test", accept=accept)
    assert result["status"] == "error"
    assert "already handled" in result["message"]
    assert state.modal_states == []


async def test_storage_closes_temporary_page_in_cancelled_anyio_scope(tools, active):
    original, ctx, _ = active
    temporary = MagicMock()

    async def new_page():
        ctx.pages.append(temporary)
        return temporary

    async def close():
        await anyio.lowlevel.checkpoint()
        ctx.pages.remove(temporary)

    ctx.new_page = new_page
    temporary.close = AsyncMock(side_effect=close)
    with anyio.CancelScope() as scope:

        async def navigate(*_args, **_kwargs):
            scope.cancel()
            await anyio.lowlevel.checkpoint()

        temporary.goto = navigate
        await tools["browser_get_local_storage"]("test", "https://storage.test")
    assert ctx.pages == [original]
    temporary.close.assert_awaited_once()


async def test_storage_preserves_primary_failure_when_cleanup_fails(tools, active, caplog):
    _, ctx, _ = active
    temporary = MagicMock(
        goto=AsyncMock(side_effect=PlaywrightError("primary navigation failed")),
        close=AsyncMock(side_effect=PlaywrightError("secondary close failed")),
    )
    ctx.new_page = AsyncMock(return_value=temporary)
    result = await tools["browser_get_local_storage"]("test", "https://storage.test")
    assert "primary navigation failed" in result["message"]
    assert "secondary close failed" in caplog.text


async def test_storage_cleanup_is_bounded_and_failure_is_visible(tools, active, monkeypatch):
    _, ctx, _ = active
    temporary = MagicMock(goto=AsyncMock(), evaluate=AsyncMock(return_value='{"value": {}}'))
    temporary.close = AsyncMock(side_effect=asyncio.Event().wait)
    ctx.new_page = AsyncMock(return_value=temporary)
    monkeypatch.setattr(cookies, "_STORAGE_CLOSE_TIMEOUT_SECONDS", 0.02, raising=False)
    result = await asyncio.wait_for(tools["browser_get_local_storage"]("test", "https://storage.test"), timeout=0.5)
    assert result["status"] == "error"
    temporary.close.assert_awaited_once()
