# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/context/context_graph.py
"""ContextGraph projection for contextual memory integration.

Tracks thread relationships, parent/child links, and semantic tags.
Deterministic and incremental.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pmm.context.semantic_tagger import extract_semantic_tags
from pmm.core.event_log import EventLog


class ContextGraph:
    """Projection for contextual relationships in the event ledger.

    Maintains mappings for threads, parent/child relationships, and semantic tags.
    Rebuildable from EventLog.read_all() and incremental via add_event().
    """

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        # thread_id -> list of event_ids (sorted for determinism)
        self.threads: Dict[str, List[int]] = {}
        # parent_event_id -> list of child event_ids
        self.children: Dict[int, List[int]] = {}
        # event_id -> list of semantic tags
        self.semantic_tags: Dict[int, List[str]] = {}
        # Track processed events for incremental updates
        self.processed_events: set[int] = set()

    def rebuild(self, events: Optional[List[Dict[str, Any]]] = None) -> None:
        """Rebuild graph from all events. Deterministic."""
        self.threads.clear()
        self.children.clear()
        self.semantic_tags.clear()
        self.processed_events.clear()

        events = events or self.eventlog.read_all()
        for event in events:
            self._add_event(event)

    def add_event(self, event: Dict[str, Any]) -> None:
        """Add single event incrementally. Idempotent."""
        event_id = event.get("id")
        if event_id in self.processed_events:
            return
        self._add_event(event)
        self.processed_events.add(event_id)

    def _add_event(self, event: Dict[str, Any]) -> None:
        """Internal: process event into graph structures."""
        event_id = event["id"]
        # Context may be provided either as a top-level "context" mapping
        # (in tests/mocks) or nested under meta["context"] for EventLog-
        # persisted events. Prefer explicit context, fall back to meta.
        context = event.get("context")
        if not context:
            context = (event.get("meta") or {}).get("context", {}) or {}

        # Thread mapping
        thread_id = context.get("thread_id")
        if thread_id:
            if thread_id not in self.threads:
                self.threads[thread_id] = []
            self.threads[thread_id].append(event_id)
            self.threads[thread_id].sort()  # Deterministic ordering

        # Parent/child relationships
        parent_id = context.get("parent_event_id")
        if parent_id is not None:
            if parent_id not in self.children:
                self.children[parent_id] = []
            self.children[parent_id].append(event_id)
            self.children[parent_id].sort()  # Deterministic

        # Semantic tags
        tags = extract_semantic_tags(event)
        if tags:
            self.semantic_tags[event_id] = tags

    # Read-only accessors for determinism
    def get_thread_events(self, thread_id: str) -> List[int]:
        """Get sorted list of event IDs for a thread."""
        return self.threads.get(thread_id, [])[:]

    def get_children(self, parent_event_id: int) -> List[int]:
        """Get sorted list of child event IDs for a parent."""
        return self.children.get(parent_event_id, [])[:]

    def get_events_with_tag(self, tag: str) -> List[int]:
        """Get sorted list of event IDs that have the given semantic tag."""
        events = [eid for eid, tags in self.semantic_tags.items() if tag in tags]
        events.sort()
        return events

    def get_semantic_tags(self, event_id: int) -> List[str]:
        """Get semantic tags for an event."""
        return self.semantic_tags.get(event_id, [])[:]
