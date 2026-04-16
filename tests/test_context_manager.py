"""Tests for justpen_browser_mcp.context_manager — registry + locks."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from justpen_browser_mcp.context_manager import ContextManager, assert_no_modal
from justpen_browser_mcp.errors import (
    ContextAlreadyExistsError,
    ContextNotFoundError,
    InvalidParamsError,
    InvalidStateFileError,
    ModalStateBlockedError,
)


def make_launcher_with_browser():
    """Helper: build a CamoufoxLauncher whose get_browser returns a mocked Browser."""
    fake_browser = MagicMock(name="Browser")

    fake_context = MagicMock(name="BrowserContext")
    fake_context.close = AsyncMock()
    fake_context.pages = []
    fake_context.new_page = AsyncMock(return_value=MagicMock(name="Page"))
    fake_context.cookies = AsyncMock(return_value=[])

    fake_browser.new_context = AsyncMock(return_value=fake_context)

    launcher = MagicMock(name="CamoufoxLauncher")
    launcher.get_browser = AsyncMock(return_value=fake_browser)
    launcher.shutdown = AsyncMock()

    return launcher, fake_browser, fake_context


class TestContextManagerCreate:
    async def test_create_first_context_calls_launcher_get_browser(self):
        launcher, browser, ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        result = await mgr.create("admin")
        assert result is ctx
        launcher.get_browser.assert_awaited_once()
        browser.new_context.assert_awaited_once()

    async def test_create_duplicate_raises(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        with pytest.raises(ContextAlreadyExistsError, match="admin"):
            await mgr.create("admin")

    async def test_create_with_state_path_passes_to_new_context(self, tmp_path):
        launcher, browser, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        state_file = tmp_path / "admin.json"
        state_file.write_text('{"cookies": [], "origins": []}')

        await mgr.create("admin", state_path=str(state_file))
        call_kwargs = browser.new_context.call_args.kwargs
        assert "storage_state" in call_kwargs
        assert call_kwargs["storage_state"] == {"cookies": [], "origins": []}


class TestContextManagerGet:
    async def test_get_returns_created_context(self):
        launcher, _, ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        assert await mgr.get("admin") is ctx

    async def test_get_unknown_raises(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        with pytest.raises(ContextNotFoundError, match="nonexistent"):
            await mgr.get("nonexistent")


class TestContextManagerLockFor:
    async def test_lock_for_returns_lock(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        lock = mgr.lock_for("admin")
        assert isinstance(lock, asyncio.Lock)

    async def test_lock_for_unknown_raises(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        with pytest.raises(ContextNotFoundError):
            mgr.lock_for("nonexistent")

    async def test_distinct_contexts_have_distinct_locks(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        await mgr.create("viewer")
        assert mgr.lock_for("admin") is not mgr.lock_for("viewer")


class TestContextManagerDestroy:
    async def test_destroy_closes_and_removes(self):
        launcher, _, ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        await mgr.destroy("admin")
        ctx.close.assert_awaited_once()
        with pytest.raises(ContextNotFoundError):
            await mgr.get("admin")

    async def test_destroy_unknown_raises(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        with pytest.raises(ContextNotFoundError):
            await mgr.destroy("nonexistent")

    async def test_destroy_last_context_shuts_down_browser(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        await mgr.destroy("admin")
        launcher.shutdown.assert_awaited_once()

    async def test_destroy_non_last_does_not_shut_down(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        await mgr.create("viewer")
        await mgr.destroy("admin")
        launcher.shutdown.assert_not_called()


class TestContextManagerList:
    async def test_list_empty(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        assert await mgr.list() == []

    async def test_list_returns_summary_per_context(self):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.pages = [MagicMock(url="https://example.com")]
        ctx.cookies = AsyncMock(return_value=[{"name": "x"}, {"name": "y"}])
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        result = await mgr.list()
        assert len(result) == 1
        entry = result[0]
        assert entry["context"] == "admin"
        assert entry["page_count"] == 1
        assert entry["active_url"] == "https://example.com"
        assert entry["cookie_count"] == 2

    async def test_list_uses_active_page_index(self):
        launcher, _, ctx = make_launcher_with_browser()
        page0 = MagicMock(url="https://a.example/")
        page1 = MagicMock(url="https://b.example/")
        ctx.pages = [page0, page1]
        ctx.cookies = AsyncMock(return_value=[])
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        mgr.state("admin").active_page_index = 1
        result = await mgr.list()
        assert result[0]["active_url"] == "https://b.example/"

    async def test_list_clamps_out_of_range_active_index(self):
        launcher, _, ctx = make_launcher_with_browser()
        page0 = MagicMock(url="https://a.example/")
        ctx.pages = [page0]
        ctx.cookies = AsyncMock(return_value=[])
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        mgr.state("admin").active_page_index = 5
        result = await mgr.list()
        assert result[0]["active_url"] == "https://a.example/"

    async def test_list_handles_concurrent_destroy(self):
        """If a context is destroyed mid-iteration (cookies() raises),
        list() should skip it and return the surviving entries rather than
        propagating the error."""
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        # Seed both contexts via the real create() path so ContextState
        # objects exist alongside the contexts (list() looks them up by name).
        await mgr.create("good")
        await mgr.create("broken")

        good_ctx = MagicMock(name="GoodCtx")
        good_ctx.pages = [MagicMock(url="https://good.example/")]
        good_ctx.cookies = AsyncMock(return_value=[{"name": "c"}])

        broken_ctx = MagicMock(name="BrokenCtx")
        broken_ctx.pages = [MagicMock(url="https://broken.example/")]
        broken_ctx.cookies = AsyncMock(side_effect=RuntimeError("context was closed"))

        mgr._contexts["good"] = good_ctx
        mgr._contexts["broken"] = broken_ctx

        result = await mgr.list()
        assert len(result) == 1
        assert result[0]["context"] == "good"
        assert result[0]["active_url"] == "https://good.example/"
        assert result[0]["cookie_count"] == 1


class TestContextManagerActivePage:
    async def test_active_page_creates_when_no_pages(self):
        launcher, _, ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        page = await mgr.active_page("admin")
        assert page is not None
        ctx.new_page.assert_awaited_once()

    async def test_active_page_returns_existing(self):
        launcher, _, ctx = make_launcher_with_browser()
        existing_page = MagicMock(name="ExistingPage")
        ctx.pages = [existing_page]
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        page = await mgr.active_page("admin")
        assert page is existing_page
        ctx.new_page.assert_not_called()

    async def test_active_page_uses_active_index(self):
        launcher, _, ctx = make_launcher_with_browser()
        page0 = MagicMock(name="Page0")
        page1 = MagicMock(name="Page1")
        ctx.pages = [page0, page1]
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        mgr.state("admin").active_page_index = 1
        page = await mgr.active_page("admin")
        assert page is page1

    async def test_active_page_clamps_out_of_range(self):
        launcher, _, ctx = make_launcher_with_browser()
        only_page = MagicMock(name="OnlyPage")
        ctx.pages = [only_page]
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        mgr.state("admin").active_page_index = 5
        page = await mgr.active_page("admin")
        assert page is only_page
        assert mgr.state("admin").active_page_index == 0

    async def test_active_page_creates_when_empty_resets_index(self):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.pages = []
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        mgr.state("admin").active_page_index = 7
        page = await mgr.active_page("admin")
        assert page is not None
        assert mgr.state("admin").active_page_index == 0
        ctx.new_page.assert_awaited()


class TestContextManagerSetActivePage:
    async def test_set_active_page_updates_index(self):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.pages = [MagicMock(), MagicMock()]
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        mgr.set_active_page("admin", 1)
        assert mgr.state("admin").active_page_index == 1

    async def test_set_active_page_out_of_range_raises(self):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.pages = [MagicMock(), MagicMock()]
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        with pytest.raises(InvalidParamsError):
            mgr.set_active_page("admin", 5)

    async def test_set_active_page_unknown_context_raises(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        with pytest.raises(ContextNotFoundError):
            mgr.set_active_page("nope", 0)


class TestContextManagerConsoleNetworkCapture:
    async def test_create_installs_page_listeners(self):
        launcher, _browser, ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        state = mgr.state("admin")
        assert state.console_messages == []
        assert state.network_requests == []
        # Verify ctx.on("page", ...) was called at least once (once for console/network,
        # once for modal state listeners — both use ctx.on("page", handler)).
        page_calls = [c for c in ctx.on.call_args_list if c[0] and c[0][0] == "page"]
        assert len(page_calls) >= 1


def _make_launcher_with_page():
    """Helper: launcher whose context has a single MagicMock page in ctx.pages."""
    launcher, browser, ctx = make_launcher_with_browser()
    page = MagicMock(name="Page")
    ctx.pages = [page]
    return launcher, browser, ctx, page


def _handler_for(page, event_name):
    """Extract the handler passed to page.on(event_name, handler)."""
    for call in page.on.call_args_list:
        if call[0] and call[0][0] == event_name:
            return call[0][1]
    return None


class TestContextManagerListenerBehavior:
    async def test_console_listener_captures_location(self):
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        handler = _handler_for(page, "console")
        assert handler is not None
        msg = MagicMock(
            type="log",
            text="hi",
            location={"url": "a.js", "lineNumber": 10, "columnNumber": 5},
        )
        handler(msg)
        assert mgr.state("admin").console_messages[-1] == {
            "type": "log",
            "text": "hi",
            "location": "a.js:10:5",
        }

    async def test_console_listener_handles_empty_location(self):
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        handler = _handler_for(page, "console")
        msg_none = MagicMock(type="log", text="a", location=None)
        handler(msg_none)
        assert mgr.state("admin").console_messages[-1]["location"] is None
        msg_empty = MagicMock(type="log", text="b", location={})
        handler(msg_empty)
        assert mgr.state("admin").console_messages[-1]["location"] is None

    async def test_pageerror_listener_captures_exception(self):
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        handler = _handler_for(page, "pageerror")
        assert handler is not None
        exc = "TypeError: boom\n  at foo.js:1:1"
        handler(exc)
        entry = mgr.state("admin").console_messages[-1]
        assert entry["type"] == "error"
        assert "TypeError" in entry["text"]
        assert entry["location"] is None

    async def test_request_listener_seeds_status_and_resource_type(self):
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        handler = _handler_for(page, "request")
        assert handler is not None
        req = MagicMock(
            url="https://x/",
            method="GET",
            resource_type="document",
        )
        handler(req)
        entry = mgr.state("admin").network_requests[-1]
        # Compare ignoring the private _id bookkeeping key.
        public = {k: v for k, v in entry.items() if not k.startswith("_")}
        assert public == {
            "url": "https://x/",
            "method": "GET",
            "status": None,
            "resource_type": "document",
            "failure": None,
        }
        assert entry["_id"] == id(req)

    async def test_response_listener_populates_status(self):
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        req_handler = _handler_for(page, "request")
        resp_handler = _handler_for(page, "response")
        assert resp_handler is not None
        req = MagicMock(url="https://x/", method="GET", resource_type="document")
        req_handler(req)
        response = MagicMock(status=200, request=req)
        resp_handler(response)
        entry = mgr.state("admin").network_requests[-1]
        assert entry["status"] == 200
        assert entry["resource_type"] == "document"

    async def test_requestfailed_listener_marks_failure(self):
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        req_handler = _handler_for(page, "request")
        fail_handler = _handler_for(page, "requestfailed")
        assert fail_handler is not None
        req = MagicMock(
            url="https://x/",
            method="GET",
            resource_type="document",
            failure="net::ERR_FAILED",
        )
        req_handler(req)
        fail_handler(req)
        entry = mgr.state("admin").network_requests[-1]
        assert entry["failure"] == "net::ERR_FAILED"
        assert entry["status"] is None

    async def test_response_listener_matches_by_request_identity(self):
        """Two concurrent requests with the same url+method must not be
        confused by the response listener even when completions arrive
        out of order — we match on id(request)."""
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        req_handler = _handler_for(page, "request")
        resp_handler = _handler_for(page, "response")

        req_a = MagicMock(
            url="https://x.com/api",
            method="GET",
            resource_type="fetch",
        )
        req_b = MagicMock(
            url="https://x.com/api",
            method="GET",
            resource_type="fetch",
        )
        req_handler(req_a)
        req_handler(req_b)

        network_requests = mgr.state("admin").network_requests
        assert len(network_requests) == 2
        assert network_requests[0]["_id"] == id(req_a)
        assert network_requests[1]["_id"] == id(req_b)
        assert network_requests[0]["_id"] != network_requests[1]["_id"]

        resp_a = MagicMock(status=200, request=req_a)
        resp_b = MagicMock(status=401, request=req_b)
        # Complete OUT OF ORDER — req_b finishes first.
        resp_handler(resp_b)
        resp_handler(resp_a)

        entry_a = next(e for e in network_requests if e["_id"] == id(req_a))
        entry_b = next(e for e in network_requests if e["_id"] == id(req_b))
        assert entry_a["status"] == 200
        assert entry_b["status"] == 401

    async def test_requestfailed_listener_matches_by_request_identity(self):
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        req_handler = _handler_for(page, "request")
        fail_handler = _handler_for(page, "requestfailed")

        req_a = MagicMock(
            url="https://x.com/api",
            method="GET",
            resource_type="fetch",
            failure="net::ERR_A",
        )
        req_b = MagicMock(
            url="https://x.com/api",
            method="GET",
            resource_type="fetch",
            failure="net::ERR_B",
        )
        req_handler(req_a)
        req_handler(req_b)
        fail_handler(req_b)
        fail_handler(req_a)

        network_requests = mgr.state("admin").network_requests
        entry_a = next(e for e in network_requests if e["_id"] == id(req_a))
        entry_b = next(e for e in network_requests if e["_id"] == id(req_b))
        assert entry_a["failure"] == "net::ERR_A"
        assert entry_b["failure"] == "net::ERR_B"

    async def test_listeners_attach_to_existing_pages(self):
        launcher, _, _ctx, page = _make_launcher_with_page()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        # The existing page should have received .on() calls for the
        # console/pageerror/request/response/requestfailed events.
        event_names = {call[0][0] for call in page.on.call_args_list if call[0]}
        assert "console" in event_names
        assert "pageerror" in event_names
        assert "request" in event_names
        assert "response" in event_names
        assert "requestfailed" in event_names


class TestContextManagerExportState:
    async def test_export_writes_storage_state_json(self, tmp_path):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.storage_state = AsyncMock(
            return_value={
                "cookies": [{"name": "session", "value": "abc"}],
                "origins": [],
            }
        )
        mgr = ContextManager(launcher)
        await mgr.create("admin")

        out_path = tmp_path / "subdir" / "admin.json"
        await mgr.export_state("admin", str(out_path))

        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["cookies"] == [{"name": "session", "value": "abc"}]

    async def test_export_unknown_context_raises(self, tmp_path):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        with pytest.raises(ContextNotFoundError):
            await mgr.export_state("nonexistent", str(tmp_path / "foo.json"))


class TestContextManagerLoadState:
    async def test_load_clears_then_adds_cookies(self, tmp_path):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.clear_cookies = AsyncMock()
        ctx.add_cookies = AsyncMock()
        ctx.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
        ctx.new_page = AsyncMock(
            return_value=MagicMock(
                goto=AsyncMock(),
                evaluate=AsyncMock(),
                close=AsyncMock(),
            )
        )
        mgr = ContextManager(launcher)
        await mgr.create("admin")

        state_file = tmp_path / "admin.json"
        state_file.write_text("""
        {
          "cookies": [{"name": "session", "value": "abc", "domain": "example.com"}],
          "origins": []
        }
        """)

        await mgr.load_state("admin", str(state_file))

        ctx.clear_cookies.assert_awaited_once()
        ctx.add_cookies.assert_awaited_once_with([{"name": "session", "value": "abc", "domain": "example.com"}])

    async def test_load_applies_local_storage_per_origin(self, tmp_path):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.clear_cookies = AsyncMock()
        ctx.add_cookies = AsyncMock()
        ctx.storage_state = AsyncMock(return_value={"cookies": [], "origins": []})
        page_mock = MagicMock(
            goto=AsyncMock(),
            evaluate=AsyncMock(),
            close=AsyncMock(),
            url="https://app.example.com",
        )
        ctx.new_page = AsyncMock(return_value=page_mock)
        mgr = ContextManager(launcher)
        await mgr.create("admin")

        state_file = tmp_path / "admin.json"
        state_file.write_text("""
        {
          "cookies": [],
          "origins": [
            {
              "origin": "https://app.example.com",
              "localStorage": [
                {"name": "auth_token", "value": "xyz123"}
              ]
            }
          ]
        }
        """)

        await mgr.load_state("admin", str(state_file))

        page_mock.goto.assert_awaited_once_with("https://app.example.com")
        page_mock.evaluate.assert_awaited_once()
        eval_arg = page_mock.evaluate.call_args[0][0]
        assert "auth_token" in eval_arg
        assert "xyz123" in eval_arg
        page_mock.close.assert_awaited_once()

    async def test_load_unknown_context_raises(self, tmp_path):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        state_file = tmp_path / "x.json"
        state_file.write_text('{"cookies": []}')
        with pytest.raises(ContextNotFoundError):
            await mgr.load_state("nonexistent", str(state_file))

    async def test_load_state_clears_local_storage_from_omitted_origin(self, tmp_path):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.clear_cookies = AsyncMock()
        ctx.add_cookies = AsyncMock()
        ctx.storage_state = AsyncMock(
            return_value={
                "cookies": [],
                "origins": [
                    {
                        "origin": "https://old.example",
                        "localStorage": [{"name": "k", "value": "v"}],
                    }
                ],
            }
        )
        page_mock = MagicMock(
            goto=AsyncMock(),
            evaluate=AsyncMock(),
            close=AsyncMock(),
            url="https://old.example",
        )
        ctx.new_page = AsyncMock(return_value=page_mock)
        mgr = ContextManager(launcher)
        await mgr.create("admin")

        state_file = tmp_path / "admin.json"
        state_file.write_text('{"cookies": [], "origins": []}')

        await mgr.load_state("admin", str(state_file))

        # Should have opened a temp page on the stale origin and cleared.
        page_mock.goto.assert_awaited_once_with("https://old.example")
        evaluate_calls = [c.args[0] for c in page_mock.evaluate.await_args_list]
        assert any("localStorage.clear()" in ev for ev in evaluate_calls)
        page_mock.close.assert_awaited()

    async def test_load_state_clears_when_new_state_has_empty_list(self, tmp_path):
        launcher, _, ctx = make_launcher_with_browser()
        ctx.clear_cookies = AsyncMock()
        ctx.add_cookies = AsyncMock()
        ctx.storage_state = AsyncMock(
            return_value={
                "cookies": [],
                "origins": [
                    {
                        "origin": "https://same.example",
                        "localStorage": [{"name": "k", "value": "v"}],
                    }
                ],
            }
        )
        page_mock = MagicMock(
            goto=AsyncMock(),
            evaluate=AsyncMock(),
            close=AsyncMock(),
            url="https://same.example",
        )
        ctx.new_page = AsyncMock(return_value=page_mock)
        mgr = ContextManager(launcher)
        await mgr.create("admin")

        state_file = tmp_path / "admin.json"
        state_file.write_text('{"cookies": [], "origins": [{"origin": "https://same.example", "localStorage": []}]}')

        await mgr.load_state("admin", str(state_file))

        page_mock.goto.assert_awaited_once_with("https://same.example")
        evaluate_calls = [c.args[0] for c in page_mock.evaluate.await_args_list]
        assert any("localStorage.clear()" in ev for ev in evaluate_calls)

    async def test_load_invalid_file_raises(self, tmp_path):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        bad = tmp_path / "bad.json"
        bad.write_text("not json at all")
        with pytest.raises(InvalidStateFileError):
            await mgr.load_state("admin", str(bad))


class TestContextManagerModalState:
    async def test_create_initializes_modal_states_buffer(self):
        launcher, _, _ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        assert mgr.state("admin").modal_states == []

    async def test_create_attaches_modal_listeners_via_on_page(self):
        launcher, _, ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        # ctx.on("page", ...) should have been called for modal listeners too
        page_calls = [c for c in ctx.on.call_args_list if c[0] and c[0][0] == "page"]
        assert len(page_calls) >= 1

    async def test_get_modal_states_empty_by_default(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        assert mgr.get_modal_states("admin") == []

    async def test_get_modal_states_returns_pending_dialog(self):
        launcher, _, _ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        # Simulate a dialog appearing
        fake_dialog = MagicMock(type="confirm", message="Are you sure?")
        mgr.state("admin").modal_states.append(
            {
                "kind": "dialog",
                "object": fake_dialog,
                "page": MagicMock(is_closed=MagicMock(return_value=False)),
            }
        )
        states = mgr.get_modal_states("admin")
        assert len(states) == 1
        assert states[0]["kind"] == "dialog"

    async def test_get_modal_states_unknown_context_raises(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        with pytest.raises(ContextNotFoundError):
            mgr.get_modal_states("nope")

    async def test_consume_modal_state_pops_dialog(self):
        launcher, _, _ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        fake_dialog = MagicMock()
        mgr.state("admin").modal_states.append(
            {
                "kind": "dialog",
                "object": fake_dialog,
                "page": MagicMock(is_closed=MagicMock(return_value=False)),
            }
        )
        consumed = mgr.consume_modal_state("admin", "dialog")
        assert consumed is not None
        assert consumed["kind"] == "dialog"
        assert mgr.state("admin").modal_states == []

    async def test_consume_modal_state_wrong_kind_returns_none(self):
        launcher, _, _ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        mgr.state("admin").modal_states.append(
            {
                "kind": "filechooser",
                "object": MagicMock(),
                "page": MagicMock(is_closed=MagicMock(return_value=False)),
            }
        )
        consumed = mgr.consume_modal_state("admin", "dialog")
        assert consumed is None
        # The filechooser entry should still be there
        assert len(mgr.state("admin").modal_states) == 1

    async def test_consume_modal_state_unknown_context_raises(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        with pytest.raises(ContextNotFoundError):
            mgr.consume_modal_state("nope", "dialog")


class TestAssertNoModal:
    async def test_no_modals_passes(self):
        launcher, _, _ = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        # Should not raise
        assert_no_modal(mgr, "admin")

    async def test_dialog_pending_raises(self):
        launcher, _, _ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        fake_dialog = MagicMock(type="confirm", message="Are you sure?")
        mgr.state("admin").modal_states.append(
            {
                "kind": "dialog",
                "object": fake_dialog,
                "page": MagicMock(is_closed=MagicMock(return_value=False)),
            }
        )
        with pytest.raises(ModalStateBlockedError, match="confirm"):
            assert_no_modal(mgr, "admin")

    async def test_filechooser_pending_raises(self):
        launcher, _, _ctx = make_launcher_with_browser()
        mgr = ContextManager(launcher)
        await mgr.create("admin")
        mgr.state("admin").modal_states.append(
            {
                "kind": "filechooser",
                "object": MagicMock(),
                "page": MagicMock(is_closed=MagicMock(return_value=False)),
            }
        )
        with pytest.raises(ModalStateBlockedError, match="file-chooser"):
            assert_no_modal(mgr, "admin")
