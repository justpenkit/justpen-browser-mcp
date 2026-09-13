"""Explicit targets preserve selection and reject expired identities."""

import asyncio
from unittest.mock import MagicMock

import pytest

from justpen_browser_mcp.errors import BrowserMcpError


@pytest.mark.asyncio
async def test_explicit_target_preserves_selection(manager):
    rec = await manager.create("target")
    first, second = MagicMock(), MagicMock()
    first.is_closed.return_value = second.is_closed.return_value = False
    rec.context.pages = [first, second]
    manager.set_active_page("target", 0)
    second_id = manager.page_id("target", second)
    async with manager.lock_for("target"):
        assert await manager.target_page("target", second_id) is second
    assert rec.state.active_page is first
    for invalid in ("missing", second_id):
        second.is_closed.return_value = True
        with pytest.raises(BrowserMcpError) as error:
            await manager.target_page("target", invalid)
        assert error.value.error_type == "page_not_found"
    rec.context.new_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_frame_ownership_and_detachment(manager):
    rec = await manager.create("target")
    owner, other, child = MagicMock(), MagicMock(), MagicMock()
    rec.context.pages = [owner, other]
    owner.is_closed.return_value = other.is_closed.return_value = False
    child.page = owner
    child.is_detached.return_value = False
    owner.frames = [owner.main_frame, child]
    other.frames = [other.main_frame]
    fid = manager.frame_id("target", child)
    assert manager.target_frame("target", owner, fid) is child
    for page in (other, owner):
        if page is owner:
            child.is_detached.return_value = True
        with pytest.raises(BrowserMcpError) as error:
            manager.target_frame("target", page, fid)
        assert error.value.error_type == "frame_not_found"


async def test_foreign_page_and_close_while_queued_never_create(manager):
    own = await manager.create("own")
    foreign = await manager.create("foreign")
    page = MagicMock()
    page.is_closed.return_value = False
    foreign.context.pages = [page]
    pid = manager.page_id("foreign", page)
    with pytest.raises(BrowserMcpError) as error:
        await manager.target_page("own", pid)
    assert error.value.error_type == "page_not_found"

    async def queued():
        async with manager.lock_for("foreign"):
            return await manager.target_page("foreign", pid)

    async with manager.lock_for("foreign"):
        task = asyncio.create_task(queued())
        await asyncio.sleep(0)
        page.is_closed.return_value = True
    with pytest.raises(BrowserMcpError) as error:
        await task
    assert error.value.error_type == "page_not_found"
    own.context.new_page.assert_not_awaited()
    foreign.context.new_page.assert_not_awaited()


async def test_omitted_page_auto_creation_is_preserved(manager):
    rec = await manager.create("empty")
    page = rec.context.new_page.return_value
    assert await manager.target_page("empty") is page
    rec.context.new_page.assert_awaited_once()


async def test_modal_filter_keeps_unmatched_objects(manager):
    rec = await manager.create("modal")
    first, second = MagicMock(), MagicMock()
    rec.context.pages = [first, second]
    second_id = manager.page_id("modal", second)
    first_state = {"kind": "dialog", "page": first}
    second_state = {"kind": "dialog", "page": second}
    rec.state.modal_states = [first_state, second_state]
    assert manager.consume_modal_state("modal", "dialog", page_id=second_id) is second_state
    assert rec.state.modal_states == [first_state]
