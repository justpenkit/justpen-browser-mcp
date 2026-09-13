"""Static headers must track instance/page identity without interception."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from justpen_browser_mcp.browser_metadata import instance_headers, page_headers
from justpen_browser_mcp.browser_runtime import BrowserRuntime
from justpen_browser_mcp.cli import build_config
from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.errors import PageNotFoundError
from justpen_browser_mcp.instance_manager import InstanceManager


def test_metadata_values_use_only_instance_and_page_identity():
    assert instance_headers("admin_1", "i1") == {
        "Justpen-Browser-Metadata-Instance-Name": "admin_1",
        "Justpen-Browser-Metadata-Instance-ID": "i1",
    }
    assert page_headers("p1") == {"Justpen-Browser-Metadata-Page-ID": "p1"}
    assert instance_headers("a%\r\nş", "i1")["Justpen-Browser-Metadata-Instance-Name"] == "a%25%0D%0A%C5%9F"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", True), ("true", True), ("1", True), ("false", False), ("0", False), (" FALSE ", False), ("invalid", True)],
)
def test_metadata_env_toggle(raw, expected):
    config = BrowserServerConfig.from_env({"BROWSER_MCP_METADATA_HEADERS_ENABLED": raw})
    assert config.metadata_headers_enabled is expected


def test_metadata_default_and_cli_overlay():
    assert BrowserServerConfig.from_env({}).metadata_headers_enabled is True
    assert (
        build_config(["--headless"], {"BROWSER_MCP_METADATA_HEADERS_ENABLED": "false"}).metadata_headers_enabled
        is False
    )


async def test_instance_headers_share_preallocated_identity(mock_launch):
    manager = InstanceManager(BrowserServerConfig())
    try:
        first = await manager.create("same")
        headers = mock_launch[-1]["kwargs"]["extra_http_headers"]
        assert headers["Justpen-Browser-Metadata-Instance-ID"] == first.instance_id
        await manager.destroy("same")
        second = await manager.create("same")
        assert second.instance_id != first.instance_id
        assert (
            mock_launch[-1]["kwargs"]["extra_http_headers"]["Justpen-Browser-Metadata-Instance-ID"]
            == second.instance_id
        )
    finally:
        await manager.shutdown_all()


def emitted_page(context):
    page = MagicMock()
    page.frames = []
    page.is_closed.return_value = False
    page.set_extra_http_headers = AsyncMock()
    context.pages.append(page)
    for registration in context.on.call_args_list:
        if registration.args[0] == "page":
            registration.args[1](page)
    return page


async def test_concurrent_pages_keep_distinct_headers_and_release_on_close(mock_launch):
    manager = InstanceManager(BrowserServerConfig())
    record = await manager.create("tabs")
    context = mock_launch[-1]["ctx"]
    try:
        first, second = emitted_page(context), emitted_page(context)
        first_id, second_id = manager.page_id("tabs", first), manager.page_id("tabs", second)
        await asyncio.gather(manager.target_page("tabs", first_id), manager.target_page("tabs", second_id))
        first.set_extra_http_headers.assert_awaited_once_with(page_headers(first_id))
        second.set_extra_http_headers.assert_awaited_once_with(page_headers(second_id))
        assert first_id != second_id
        context.pages.remove(first)
        first.is_closed.return_value = True
        for registration in first.on.call_args_list:
            if registration.args[0] == "close":
                registration.args[1](first)
        assert first not in record.state.page_header_tasks
        replacement = emitted_page(context)
        assert manager.page_id("tabs", replacement) != first_id
    finally:
        await manager.shutdown_all()


async def test_header_setup_failure_is_visible_to_target_caller(mock_launch):
    manager = InstanceManager(BrowserServerConfig())
    await manager.create("failure")
    page = emitted_page(mock_launch[-1]["ctx"])
    page.set_extra_http_headers.side_effect = RuntimeError("header setup failed")
    try:
        with pytest.raises(RuntimeError, match="header setup failed"):
            await manager.target_page("failure")
    finally:
        await manager.shutdown_all()


async def test_target_cancellation_preserves_owned_setup_until_destroy(mock_launch):
    manager = InstanceManager(BrowserServerConfig())
    record = await manager.create("cancel")
    page = emitted_page(mock_launch[-1]["ctx"])
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def setup(_headers):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    page.set_extra_http_headers.side_effect = setup
    target = asyncio.create_task(manager.target_page("cancel"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        target.cancel()
        await asyncio.gather(target, return_exceptions=True)
        assert not cancelled.is_set()
        await manager.destroy("cancel")
        assert cancelled.is_set()
        assert not record.state.page_header_tasks
    finally:
        target.cancel()
        await asyncio.gather(target, return_exceptions=True)
        await manager.shutdown_all()


async def test_page_close_during_setup_is_target_error_not_operation_cancellation(mock_launch):
    manager = InstanceManager(BrowserServerConfig())
    await manager.create("closing-page")
    context = mock_launch[-1]["ctx"]
    page = emitted_page(context)
    started = asyncio.Event()

    async def setup(_headers):
        started.set()
        await asyncio.Future()

    page.set_extra_http_headers.side_effect = setup
    target = asyncio.create_task(manager.target_page("closing-page"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        context.pages.remove(page)
        page.is_closed.return_value = True
        for registration in page.on.call_args_list:
            if registration.args[0] == "close":
                registration.args[1](page)
        with pytest.raises(PageNotFoundError):
            await target
        assert not target.cancelled()
    finally:
        target.cancel()
        await asyncio.gather(target, return_exceptions=True)
        await manager.shutdown_all()


async def test_disabled_metadata_does_not_install_headers(mock_launch):
    manager = InstanceManager(BrowserServerConfig(metadata_headers_enabled=False))
    try:
        await manager.create("off")
        assert mock_launch[-1]["kwargs"].get("extra_http_headers") is None
    finally:
        await manager.shutdown_all()


async def test_runtime_selection_is_reused_for_each_instance(mock_launch):
    runtime = BrowserRuntime(
        version="152.0.4-beta.30", executable_path="/chosen/browser", installation="browsers/official/latest-asset"
    )
    manager = InstanceManager(BrowserServerConfig(), browser_runtime=runtime)
    try:
        await manager.create("a")
        await manager.create("b")
        assert [item["kwargs"]["browser_runtime"] for item in mock_launch] == [runtime, runtime]
    finally:
        await manager.shutdown_all()


async def test_page_initialization_precedes_controlled_target_use(mock_launch):
    manager = InstanceManager(BrowserServerConfig())
    await manager.create("page")
    page = MagicMock()
    page.is_closed.return_value = False
    page.frames = []
    started, release = asyncio.Event(), asyncio.Event()

    async def set_headers(headers):
        assert headers == {"Justpen-Browser-Metadata-Page-ID": manager.page_id("page", page)}
        started.set()
        await release.wait()

    page.set_extra_http_headers = AsyncMock(side_effect=set_headers)
    mock_launch[-1]["ctx"].pages = [page]
    task = asyncio.create_task(manager.target_page("page"))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not task.done()
        release.set()
        assert await task is page
        await manager.target_page("page")
        assert page.set_extra_http_headers.await_count == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await manager.shutdown_all()
