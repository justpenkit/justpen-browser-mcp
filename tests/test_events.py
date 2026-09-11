"""Bounded browser evidence retains honest cursors and complete field-size metadata."""

import importlib

import pytest


def buffer(capacity=3):
    return importlib.import_module("justpen_browser_mcp.events").EventBuffer(capacity)


def test_retention_reports_lost_history_and_bounds_stored_records():
    events = buffer(2)
    events.append({"text": "one"})
    first = events.page(limit=1)
    events.append({"text": "two"})
    events.append({"text": "three"})
    events.append({"text": "four"})
    result = events.page(after=first["next_cursor"], limit=10)
    assert len(events) == 2
    assert [item["text"] for item in result["items"]] == ["three", "four"]
    assert result["dropped_count"] == 2
    assert result["retention_lost"] is True


def test_pagination_does_not_skip_matching_records_or_repeat_old_results():
    events = buffer(10)
    for text in ("skip", "yes-one", "skip", "yes-two", "skip"):
        events.append({"text": text})

    def select(entry):
        return entry["text"].startswith("yes")

    first = events.page(limit=1, predicate=select)
    second = events.page(after=first["next_cursor"], limit=1, predicate=select)
    empty = events.page(after=second["next_cursor"], limit=1, predicate=select)
    assert [row["text"] for row in first["items"]] == ["yes-one"]
    assert first["has_more"] is True
    assert [row["text"] for row in second["items"]] == ["yes-two"]
    assert second["has_more"] is False
    assert empty["items"] == []
    assert empty["next_cursor"] == second["next_cursor"]


def test_pending_request_update_appears_after_an_earlier_cursor():
    events = buffer()
    pending = events.append({"request_id": "one", "status": None, "_id": 10})
    before = events.page(limit=10)
    updated = events.update(pending, {"status": 200})
    after = events.page(after=before["next_cursor"], limit=10)
    assert len(events) == 1
    assert updated["status"] == 200
    assert after["items"][0]["status"] == 200
    assert after["items"][0]["request_id"] == "one"
    assert "_id" not in after["items"][0]
    assert after["dropped_count"] == 0


def test_large_event_fields_are_bounded_and_explicitly_marked():
    events = buffer()
    events.append({"text": "x" * 100_000, "type": "log"})
    row = events.page(limit=1)["items"][0]
    assert len(row["text"]) <= 4096
    assert row["truncated_fields"] == ["text"]


@pytest.mark.parametrize("limit", [0, -1, 501])
def test_invalid_page_limits_are_rejected(limit):
    with pytest.raises(ValueError):
        buffer().page(limit=limit)


def test_cursor_from_a_different_instance_stream_is_rejected():
    first = buffer()
    first.append({"text": "one"})
    cursor = first.page(limit=1)["next_cursor"]
    with pytest.raises(ValueError, match="cursor"):
        buffer().page(after=cursor, limit=1)
