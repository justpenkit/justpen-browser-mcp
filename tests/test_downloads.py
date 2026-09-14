"""Behavior tests for bounded download evidence."""

from unittest.mock import MagicMock

import pytest

from justpen_browser_mcp.downloads import DownloadRegistry
from justpen_browser_mcp.errors import DownloadNotFoundError


def download(url: str, filename: str) -> MagicMock:
    return MagicMock(url=url, suggested_filename=filename)


def test_download_identity_is_stable_until_handle_eviction() -> None:
    registry = DownloadRegistry(capacity=1)
    first = download("https://example.test/a", "a.txt")
    second = download("https://example.test/b", "b.txt")

    first_id = registry.register(first, "page-a")
    assert registry.register(first, "page-a") == first_id

    second_id = registry.register(second, "page-b")
    assert second_id != first_id
    assert registry.id_for(first) is None
    assert registry.page()["items"][-1] == {
        "download_id": second_id,
        "page_id": "page-b",
        "url": "https://example.test/b",
        "suggested_filename": "b.txt",
        "status": "detected",
        "created_at": registry.page()["items"][-1]["created_at"],
        "sequence": 2,
        "timestamp": registry.page()["items"][-1]["timestamp"],
        "available": True,
    }


def test_page_filters_and_paginates_with_event_cursor() -> None:
    registry = DownloadRegistry(capacity=3)
    first_id = registry.register(download("https://example.test/a", "a.txt"), "page-a")
    registry.register(download("https://example.test/b", "b.txt"), "page-b")
    third_id = registry.register(download("https://example.test/c", "c.txt"), "page-a")

    first_page = registry.page(page_id="page-a", limit=1)
    second_page = registry.page(page_id="page-a", after=first_page["next_cursor"], limit=1)

    assert [item["download_id"] for item in first_page["items"]] == [first_id]
    assert [item["download_id"] for item in second_page["items"]] == [third_id]
    assert first_page["has_more"] is True
    assert second_page["has_more"] is False


def test_pinned_oldest_survives_handle_eviction_and_lifecycle_updates(tmp_path) -> None:
    registry = DownloadRegistry(capacity=2)
    first_id = registry.register(download("https://example.test/a", "a.txt"), "page-a")
    second = download("https://example.test/b", "b.txt")
    second_id = registry.register(second, "page-b")
    assert first_id is not None
    assert second_id is not None

    record = registry.pin(first_id)
    assert record.status == "saving"
    third_id = registry.register(download("https://example.test/c", "c.txt"), "page-c")

    assert registry.id_for(second) is None
    assert record.pinned is True
    saved_path = str(tmp_path / "a.txt")
    registry.finish(first_id, path=saved_path)
    registry.unpin(first_id)
    by_id = {item["download_id"]: item for item in registry.page()["items"]}
    assert by_id[first_id]["status"] == "saved"
    assert by_id[first_id]["path"] == saved_path
    assert by_id[first_id]["available"] is True
    assert by_id[third_id]["available"] is True


def test_all_pinned_overflow_is_counted_without_growing_handles() -> None:
    registry = DownloadRegistry(capacity=1)
    first_id = registry.register(download("https://example.test/a", "a.txt"), "page-a")
    assert first_id is not None
    registry.pin(first_id)

    assert registry.register(download("https://example.test/b", "b.txt"), "page-b") is None
    page = registry.page()
    assert page["dropped_count"] == 1
    assert len(page["items"]) == 1


def test_cancelled_save_returns_to_detected_and_missing_id_is_rejected() -> None:
    registry = DownloadRegistry(capacity=1)
    download_id = registry.register(download("https://example.test/a", "a.txt"), "page-a")
    assert download_id is not None
    registry.pin(download_id)
    registry.unpin(download_id)

    assert registry.page()["items"][0]["status"] == "detected"
    with pytest.raises(DownloadNotFoundError):
        registry.pin("foreign")


def test_clear_releases_handles_but_retained_metadata_is_unavailable() -> None:
    registry = DownloadRegistry(capacity=1)
    item = download("https://example.test/a", "a.txt")
    download_id = registry.register(item, "page-a")

    registry.clear()

    assert registry.id_for(item) is None
    assert registry.page()["items"][0]["download_id"] == download_id
    assert registry.page()["items"][0]["available"] is False


@pytest.mark.parametrize("capacity", [0, -1])
def test_capacity_must_be_positive(capacity: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        DownloadRegistry(capacity)
