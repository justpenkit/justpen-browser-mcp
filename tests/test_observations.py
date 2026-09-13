"""Typed action observation and lifecycle regressions."""

import asyncio
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import TypeAdapter, ValidationError

from justpen_browser_mcp.observation_models import ResponseWait, WaitForSpec
from justpen_browser_mcp.observations import run_observed_action

ADAPTER = TypeAdapter(WaitForSpec)


@pytest.mark.parametrize(
    ("kind", "fields"),
    [
        ("response", {"url": "u"}),
        ("url", {"url": "u"}),
        ("element", {"selector": "x"}),
        ("text", {"text": "x"}),
        ("popup", {}),
        ("download", {}),
    ],
)
def test_kinds(kind, fields):
    assert ADAPTER.validate_python({"kind": kind, **fields}).kind == kind
    assert ADAPTER.json_schema()["discriminator"]["propertyName"] == "kind"


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"kind": "popup", "url": "x"},
        {"kind": "popup", "timeout_ms": 0},
        {"kind": "popup", "timeout_ms": True},
        {"kind": "response", "url": ""},
        {"kind": "text", "text": ""},
        {"kind": "element", "selector": ""},
        {"kind": "response", "url": "x", "status": 99},
        {"kind": "response", "url": "x", "status": True},
        *[{"kind": "response", "url": "x", "method": method} for method in ["", "GET POST", "GÉT", "GET\n"]],
    ],
)
def test_reject_invalid(fields):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(fields)


def test_method_normalized():
    assert ResponseWait(kind="response", url="u", method="post").method == "POST"


class Emitter:
    def __init__(self):
        self.callbacks = defaultdict(list)
        self.main_frame = SimpleNamespace(page=self, url="old")

    def on(self, event, callback):
        self.callbacks[event].append(callback)

    def remove_listener(self, event, callback):
        self.callbacks[event].remove(callback)

    def emit(self, event, value=None):
        for callback in list(self.callbacks[event]):
            callback(value)


@pytest.fixture
def environment():
    page = Emitter()
    manager = MagicMock()
    manager.page_id.return_value = "page-1"
    manager.frame_id.return_value = "frame-1"
    manager.state.return_value.network_request_index = {}
    return page, page.main_frame, manager


@pytest.mark.asyncio
async def test_immediate_response_and_cleanup(environment):
    page, frame, manager = environment
    request = SimpleNamespace(frame=frame, method="POST", url="https://example.test/save")
    manager.state.return_value.network_request_index[id(request)] = {"request_id": "retained"}

    async def perform():
        page.emit("request", request)
        page.emit("response", SimpleNamespace(request=request, url=request.url, status=201))
        return {"clicked": True}

    action = AsyncMock(side_effect=perform)
    result = await run_observed_action(
        "example", manager, page, frame, action, ResponseWait(kind="response", url=request.url, method="post")
    )
    assert result["data"]["observation"]["matched"] is True
    assert result["data"]["observation"]["request_id"] == "retained"
    assert action.await_count == 1
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["early", "frame", "page", "status"])
async def test_response_non_matches(environment, case):
    page, frame, manager = environment
    owner = frame if case in {"early", "status"} else SimpleNamespace(page=page if case == "frame" else Emitter())
    request = SimpleNamespace(frame=owner, method="GET", url="u")

    async def action():
        if case != "early":
            page.emit("request", request)
        page.emit("response", SimpleNamespace(request=request, url="u", status=500 if case == "status" else 200))
        return {"clicked": True}

    result = await run_observed_action(
        "example",
        manager,
        page,
        frame,
        action,
        ResponseWait(kind="response", url="u", status=200, timeout_ms=1),
        explicit_frame=True,
    )
    assert result["error_type"] == "observation_timeout"
    assert result["data"]["action_completed"] is True
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["close", "crash"])
async def test_target_termination(environment, event):
    page, frame, manager = environment

    async def action():
        page.emit(event)
        return {}

    result = await run_observed_action("example", manager, page, frame, action, ResponseWait(kind="response", url="u"))
    assert result["error_type"] == "internal_error"
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ValueError, asyncio.CancelledError])
async def test_action_failure_cleans_up(environment, error):
    page, frame, manager = environment
    with pytest.raises(error):
        await run_observed_action(
            "example", manager, page, frame, AsyncMock(side_effect=error), ResponseWait(kind="response", url="u")
        )
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["popup", "download", "url"])
async def test_immediate_events(environment, kind):
    page, frame, manager = environment
    manager.state.return_value.downloads.id_for.return_value = "download-1"
    spec = ADAPTER.validate_python({"kind": kind, **({"url": "next"} if kind == "url" else {})})

    async def action():
        if kind == "url":
            frame.url = "next"
            page.emit("framenavigated", frame)
        elif kind == "popup":
            page.emit("popup", Emitter())
        else:
            page.emit("download", SimpleNamespace(suggested_filename="report.txt"))
        return {}

    result = await run_observed_action("example", manager, page, frame, action, spec)
    assert result["data"]["observation"]["matched"] is True
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
async def test_download_overflow(environment):
    page, frame, manager = environment
    manager.state.return_value.downloads.id_for.return_value = None

    async def action():
        page.emit("download", SimpleNamespace(suggested_filename="report.txt"))
        return {}

    result = await run_observed_action(
        "example", manager, page, frame, action, ADAPTER.validate_python({"kind": "download"})
    )
    assert result["error_type"] == "download_not_found"
    assert result["data"]["action_completed"] is True


@pytest.mark.asyncio
async def test_url_requires_subsequent_chosen_frame_event(environment):
    page, frame, manager = environment
    frame.url = "next"

    async def action():
        page.emit("framenavigated", SimpleNamespace(url="next", page=page))
        return {}

    result = await run_observed_action(
        "example",
        manager,
        page,
        frame,
        action,
        ADAPTER.validate_python({"kind": "url", "url": "next", "timeout_ms": 1}),
    )
    assert result["error_type"] == "observation_timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "state"), [("element", "visible"), ("text", "visible"), ("text", "hidden")])
async def test_postcondition_starts_after_completed_action(environment, kind, state):
    page, frame, manager = environment
    completed = False

    async def wait_for(**kwargs):
        assert completed
        assert kwargs == {"state": state, "timeout": 0}

    locator = MagicMock()
    locator.wait_for = AsyncMock(side_effect=wait_for)
    locator.first = locator
    locator.filter.return_value = locator
    frame.locator = MagicMock(return_value=locator)
    frame.get_by_text = MagicMock(return_value=locator)

    async def action():
        nonlocal completed
        completed = True
        return {}

    spec = ADAPTER.validate_python({"kind": kind, "state": state, "selector" if kind == "element" else "text": "ok"})
    result = await run_observed_action("example", manager, page, frame, action, spec)
    assert result["data"]["observation"]["matched"] is True
    if kind == "text":
        locator.filter.assert_called_once_with(visible=True)
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
async def test_cancel_during_observation_cleans_up_and_ignores_late_callback(environment):
    page, frame, manager = environment
    completed = asyncio.Event()

    async def action():
        completed.set()
        return {}

    task = asyncio.create_task(
        run_observed_action("example", manager, page, frame, action, ResponseWait(kind="response", url="u"))
    )
    await completed.wait()
    callback = page.callbacks["request"][0]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    callback(SimpleNamespace(frame=frame, method="GET", url="u"))
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
async def test_none_preserves_old_response(environment):
    page, frame, manager = environment
    result = await run_observed_action("example", manager, page, frame, AsyncMock(return_value={"clicked": True}), None)
    assert result == {"status": "success", "instance": "example", "data": {"clicked": True}}
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
async def test_state_wait_cancellation_drains_waiter(environment):
    page, frame, manager = environment
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def wait_for(**kwargs):
        started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    locator = SimpleNamespace(wait_for=wait_for)
    frame.locator = lambda selector: locator
    task = asyncio.create_task(
        run_observed_action(
            "example",
            manager,
            page,
            frame,
            AsyncMock(return_value={}),
            ADAPTER.validate_python({"kind": "element", "selector": "x"}),
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    assert not any(page.callbacks.values())


@pytest.mark.asyncio
async def test_evicted_network_record_has_no_fabricated_id(environment):
    page, frame, manager = environment
    request = SimpleNamespace(frame=frame, method="GET", url="u")

    async def action():
        page.emit("request", request)
        page.emit("response", SimpleNamespace(request=request, url="u", status=200))
        return {}

    result = await run_observed_action("example", manager, page, frame, action, ResponseWait(kind="response", url="u"))
    assert result["data"]["observation"]["request_id"] is None


@pytest.mark.asyncio
async def test_completed_marker_precedes_observation_timeout(environment):
    page, frame, manager = environment
    markers = []
    result = await run_observed_action(
        "example",
        manager,
        page,
        frame,
        AsyncMock(return_value={"clicked": True}),
        ResponseWait(kind="response", url="u", timeout_ms=1),
        on_action_completed=lambda data, kind: markers.append((data, kind)),
    )
    assert result["error_type"] == "observation_timeout"
    assert markers == [({"clicked": True}, "response")]
