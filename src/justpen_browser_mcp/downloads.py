"""Bounded identities and lifecycle metadata for browser downloads."""

from __future__ import annotations

import uuid
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from .errors import DownloadFailedError, DownloadNotFoundError
from .events import EventBuffer

if TYPE_CHECKING:
    from playwright.async_api import Download

DownloadStatus = Literal["detected", "saving", "saved", "failed"]


@dataclass
class DownloadRecord:
    """Retained Playwright handle and server-observed save state."""

    download_id: str
    page_id: str
    download: Download
    status: DownloadStatus
    created_at: str
    pinned: bool = False


class DownloadRegistry:
    """Retain a bounded set of download handles and paged metadata."""

    def __init__(self, capacity: int) -> None:
        """Create a registry with equal handle and metadata bounds."""
        if capacity < 1:
            raise ValueError("Download capacity must be positive.")
        self.capacity = capacity
        self._records: OrderedDict[str, DownloadRecord] = OrderedDict()
        self._object_ids: weakref.WeakKeyDictionary[Download, str] = weakref.WeakKeyDictionary()
        self._events = EventBuffer(capacity)
        self._event_by_id: dict[str, dict[str, Any]] = {}

    def register(self, download: Download, page_id: str) -> str | None:
        """Assign a stable ID, evicting the oldest handle that is not saving."""
        existing = self.id_for(download)
        if existing is not None:
            return existing
        if len(self._records) >= self.capacity:
            evicted_id = next((key for key, record in self._records.items() if not record.pinned), None)
            if evicted_id is None:
                self._events.dropped_count += 1
                return None
            evicted = self._records.pop(evicted_id)
            self._object_ids.pop(evicted.download, None)

        download_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()
        record = DownloadRecord(download_id, page_id, download, "detected", created_at)
        self._records[download_id] = record
        self._object_ids[download] = download_id
        event = self._events.append(
            {
                "download_id": download_id,
                "page_id": page_id,
                "url": download.url,
                "suggested_filename": download.suggested_filename,
                "status": "detected",
                "created_at": created_at,
            }
        )
        self._event_by_id[download_id] = event
        self._prune_event_references()
        return download_id

    def id_for(self, download: Download) -> str | None:
        """Return the object's ID only while its registry handle remains available."""
        download_id = self._object_ids.get(download)
        return download_id if download_id in self._records else None

    def page(self, *, after: str | None = None, limit: int = 100, page_id: str | None = None) -> dict[str, Any]:
        """Return retained metadata, annotating whether each handle is still usable."""
        result = self._events.page(
            after=after,
            limit=limit,
            predicate=None if page_id is None else lambda item: item["page_id"] == page_id,
        )
        for item in result["items"]:
            item["available"] = item["download_id"] in self._records
        return result

    def pin(self, download_id: str) -> DownloadRecord:
        """Prevent a retained handle from eviction for the duration of a save."""
        record = self._records.get(download_id)
        if record is None:
            raise DownloadNotFoundError(f"Download {download_id!r} is not available.")
        if record.pinned:
            raise DownloadFailedError(f"Download {download_id!r} is already being saved.")
        record.pinned = True
        record.status = "saving"
        event = self._event_by_id.get(download_id)
        if event is not None:
            event.pop("failure", None)
        self._update_event(record, {"status": "saving"})
        return record

    def finish(self, download_id: str, *, path: str | None = None, failure: str | None = None) -> None:
        """Record the confirmed result of a pinned save operation."""
        record = self._records.get(download_id)
        if record is None:
            raise DownloadNotFoundError(f"Download {download_id!r} is not available.")
        record.status = "failed" if failure is not None else "saved"
        changes: dict[str, Any] = {"status": record.status}
        if path is not None:
            changes["path"] = path
        if failure is not None:
            changes["failure"] = failure
        else:
            event = self._event_by_id.get(download_id)
            if event is not None:
                event.pop("failure", None)
        self._update_event(record, changes)

    def unpin(self, download_id: str) -> None:
        """Release a save pin and reset an unconfirmed attempt to detected."""
        record = self._records.get(download_id)
        if record is None:
            return
        record.pinned = False
        if record.status == "saving":
            record.status = "detected"
            self._update_event(record, {"status": "detected"})

    def clear(self) -> None:
        """Release every Playwright handle while leaving bounded audit metadata readable."""
        self._records.clear()
        self._object_ids.clear()

    def _update_event(self, record: DownloadRecord, changes: dict[str, Any]) -> None:
        event = self._event_by_id.get(record.download_id)
        if event is None:
            return
        updated = self._events.update(event, changes)
        self._event_by_id[record.download_id] = updated
        self._prune_event_references()

    def _prune_event_references(self) -> None:
        retained = {item["download_id"] for item in self._events}
        self._event_by_id = {key: value for key, value in self._event_by_id.items() if key in retained}
