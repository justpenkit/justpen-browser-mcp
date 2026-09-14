"""Stable frame identities follow attachment, not document navigation."""

from unittest.mock import MagicMock


async def test_frame_events_register_detach_and_cleanup(manager):
    rec = await manager.create("frames")
    page = MagicMock()
    main, child, replacement = MagicMock(), MagicMock(), MagicMock()
    page.is_closed.return_value = False
    page.main_frame = main
    page.frames = [main, child]
    rec.context.pages = [page]
    for frame in (main, child, replacement):
        frame.page = page
        frame.is_detached.return_value = False
    attaches = [args[0][1] for args in rec.context.on.call_args_list if args[0][0] == "page"]
    for callback in attaches:
        callback(page)
    first = manager.frame_id("frames", child)
    child.url = "https://example.test/next"
    assert manager.frame_id("frames", child) == first
    events = {args[0][0]: args[0][1] for args in page.on.call_args_list}
    events["framedetached"](child)
    assert child not in rec.state.frame_ids
    events["frameattached"](replacement)
    assert manager.frame_id("frames", replacement) != first
    rec.context.pages = []
    events["close"](page)
    assert rec.state.frame_ids == {}
