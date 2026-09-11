"""Bounded browser event streams with resumable, instance-specific cursors."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

MAX_EVENT_FIELD_CHARS = 4096
MAX_EVENT_PAGE_SIZE = 500


class EventBuffer:
    """Retain recent records and make eviction and truncated fields explicit."""

    def __init__(self, capacity: int = 1000) -> None:
        """Create one independently identified console or network stream."""
        if capacity < 1:
            raise ValueError("Event capacity must be positive.")
        self.capacity = capacity
        self.stream_id = uuid.uuid4().hex
        self.dropped_count = 0
        self._sequence = 0
        self._last_evicted = 0
        self._entries: deque[dict[str, Any]] = deque()

    def __len__(self) -> int:
        """Return the number of retained records."""
        return len(self._entries)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Iterate in current event sequence order."""
        return iter(self._entries)

    def __getitem__(self, index: int) -> dict[str, Any]:
        """Access a retained record for the manager's bounded request index."""
        return self._entries[index]

    def append(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Store a bounded copy and return its manager-owned record."""
        item = dict(entry)
        truncated = set(item.get("truncated_fields", []))
        for key, value in item.items():
            if isinstance(value, str) and len(value) > MAX_EVENT_FIELD_CHARS:
                item[key] = value[:MAX_EVENT_FIELD_CHARS]
                truncated.add(key)
        if truncated:
            item["truncated_fields"] = sorted(truncated)
        self._sequence += 1
        item["sequence"] = self._sequence
        item["timestamp"] = datetime.now(UTC).isoformat()
        if len(self._entries) >= self.capacity:
            self._last_evicted = self._entries.popleft()["sequence"]
            self.dropped_count += 1
        self._entries.append(item)
        return item

    def update(self, entry: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
        """Resurface a pending request's latest state for incremental consumers."""
        self._entries.remove(entry)
        return self.append({**entry, **changes})

    def _cursor_sequence(self, cursor: str | None) -> int:
        if cursor is None:
            return 0
        stream, separator, sequence = cursor.rpartition(":")
        if not separator or stream != self.stream_id:
            raise ValueError("Invalid cursor for this instance/event stream.")
        try:
            number = int(sequence)
        except ValueError as error:
            raise ValueError("Invalid event cursor sequence.") from error
        if number < 0 or number > self._sequence:
            raise ValueError("Event cursor is outside this stream's sequence.")
        return number

    def page(
        self,
        *,
        after: str | None = None,
        limit: int = 100,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        """Read bounded records; reuse the cursor with the same filtering options."""
        if not 1 <= limit <= MAX_EVENT_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_EVENT_PAGE_SIZE}.")
        sequence = self._cursor_sequence(after)
        matches = [
            item for item in self._entries if item["sequence"] > sequence and (predicate is None or predicate(item))
        ]
        selected = matches[:limit]
        has_more = len(matches) > limit
        last = selected[-1]["sequence"] if has_more else self._sequence
        return {
            "items": [{key: value for key, value in item.items() if not key.startswith("_")} for item in selected],
            "next_cursor": f"{self.stream_id}:{last}",
            "has_more": has_more,
            "retained_count": len(self._entries),
            "dropped_count": self.dropped_count,
            "retention_lost": sequence < self._last_evicted,
        }
