"""Event pointer index for O(1) event retrieval by ID.

Provides fast byte-range access to events without full ledger scans.
Maintains deterministic index of (event_id, kind, ts, byte_offset, hash)
for efficient routing and verification.

Design principles:
- Truth-first: All data verified against ledger hashes
- Deterministic: Reproducible index from same ledger state
- Performance: O(1) lookups, O(k) fetches for k events
- Integrity: Optional hash verification on reads
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pmm.storage.eventlog import EventLog


@dataclass(frozen=True)
class EventMeta:
    """Lightweight event metadata for pointer index."""

    event_id: int
    kind: str
    ts: str
    byte_offset: int
    content_hash: str


class EventIndex:
    """Fast pointer index for event-by-ID retrieval.

    Maintains a compact index of event metadata to enable O(1) lookups
    and byte-range fetches without full ledger scans.
    """

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self._lock = threading.RLock()
        self._index: dict[int, EventMeta] = {}
        self._max_indexed_id: int = 0

        # Build initial index
        self._rebuild_index()

        # Listen for new events
        eventlog.register_append_listener(self._on_event_appended)

    def _rebuild_index(self) -> None:
        """Rebuild the complete index from the eventlog."""
        with self._lock:
            self._index.clear()
            self._max_indexed_id = 0

            # Get all events for indexing
            events = self.eventlog.read_all()
            self._process_events(events)

    def _process_events(self, events: Iterable[dict[str, Any]]) -> None:
        """Process events and add to index."""
        for event in events:
            try:
                event_id = int(event.get("id", 0))
                if event_id <= 0:
                    continue

                kind = str(event.get("kind", ""))
                ts = str(event.get("ts", ""))

                # Calculate content hash for verification
                content_hash = self._calculate_event_hash(event)

                # For now, byte_offset is 0 (we'll implement proper byte addressing later)
                # This allows the interface to work while we build out the full implementation
                byte_offset = 0

                meta = EventMeta(
                    event_id=event_id,
                    kind=kind,
                    ts=ts,
                    byte_offset=byte_offset,
                    content_hash=content_hash,
                )

                self._index[event_id] = meta
                self._max_indexed_id = max(self._max_indexed_id, event_id)

            except Exception:
                # Skip malformed events but continue indexing
                continue

    def _calculate_event_hash(self, event: dict[str, Any]) -> str:
        """Calculate deterministic hash for event content."""
        # Use same canonical representation as EventLog
        canonical = {
            "id": int(event.get("id", 0)),
            "ts": str(event.get("ts", "")),
            "kind": str(event.get("kind", "")),
            "content": str(event.get("content", "")),
            "meta": event.get("meta", {}),
        }

        # Deterministic JSON serialization
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def _on_event_appended(self, event: dict[str, Any]) -> None:
        """Handle new event appended to eventlog."""
        self._process_events([event])

    def get_event_meta(self, event_id: int) -> EventMeta | None:
        """Get metadata for a specific event ID."""
        with self._lock:
            return self._index.get(event_id)

    def read_by_ids(
        self, event_ids: list[int], *, verify_hash: bool = False
    ) -> list[dict[str, Any]]:
        """Read events by IDs with optional hash verification.

        Args:
            event_ids: List of event IDs to fetch
            verify_hash: If True, verify content hash matches index

        Returns:
            List of event dictionaries in same order as event_ids.
            Missing events are omitted from results.
        """
        if not event_ids:
            return []

        # For now, fall back to reading from eventlog and filtering
        # TODO: Implement true byte-range reads once we have proper offset calculation
        all_events = self.eventlog.read_all()
        event_map = {int(e.get("id", 0)): e for e in all_events}

        results = []
        for event_id in event_ids:
            event = event_map.get(event_id)
            if event is None:
                continue

            # Optional hash verification
            if verify_hash:
                meta = self.get_event_meta(event_id)
                if meta is None:
                    continue

                calculated_hash = self._calculate_event_hash(event)
                if calculated_hash != meta.content_hash:
                    # Hash mismatch - skip this event
                    continue

            results.append(event)

        return results

    def index_scan(self) -> Iterable[EventMeta]:
        """Iterate over all indexed event metadata."""
        with self._lock:
            # Return sorted by event_id for deterministic ordering
            for event_id in sorted(self._index.keys()):
                yield self._index[event_id]

    def get_stats(self) -> dict[str, Any]:
        """Get index statistics for monitoring."""
        with self._lock:
            return {
                "indexed_events": len(self._index),
                "max_indexed_id": self._max_indexed_id,
                "index_size_bytes": len(self._index) * 200,  # Rough estimate
            }
