"""Event router for semantic-based event retrieval.

Transforms MemeGraph from payload mirror to semantic router.
Stores event_id pointers and provides routing based on content similarity,
recency, and structural relationships.

Design principles:
- Router, not mirror: Store pointers, not payloads
- Semantic routing: Content-based candidate selection
- Recency bias: Recent events weighted higher
- Deterministic: Reproducible routing from same inputs
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from pmm.storage.event_index import EventIndex
from pmm.storage.eventlog import EventLog

logger = logging.getLogger("pmm.runtime.event_router")


@dataclass(frozen=True)
class ContextQuery:
    """Query specification for event routing."""

    # Required event kinds (always include if present)
    required_kinds: list[str]

    # Semantic query terms for content matching
    semantic_terms: list[str]

    # Maximum events to return
    limit: int = 10

    # Recency boost factor (0.0 = no bias, 1.0 = strong recency bias)
    recency_boost: float = 0.3

    # Diversity factor (0.0 = no diversity, 1.0 = maximum diversity)
    diversity: float = 0.1


@dataclass(frozen=True)
class EventPointer:
    """Lightweight event pointer for routing."""

    event_id: int
    kind: str
    ts: str
    content_summary: str  # First 100 chars for semantic matching
    semantic_score: float = 0.0
    recency_score: float = 0.0
    final_score: float = 0.0


class EventRouter:
    """Semantic router for event retrieval without full payload storage.

    Replaces tail-constrained reads with intelligent routing based on:
    - Content similarity (semantic matching)
    - Event importance (kind-based priorities)
    - Recency bias (recent events weighted higher)
    - Structural relationships (commitment chains, etc.)
    """

    def __init__(self, eventlog: EventLog, event_index: EventIndex) -> None:
        self.eventlog = eventlog
        self.event_index = event_index
        self._lock = threading.RLock()

        # Lightweight event pointers for routing
        self._pointers: dict[int, EventPointer] = {}

        # Semantic indices for fast content matching
        self._kind_index: dict[str, list[int]] = {}
        self._content_terms: dict[int, set[str]] = {}

        # Structural indices (preserved from original MemeGraph)
        self._identity_timeline: list[int] = []  # event_ids of identity_adopt events
        self._commitment_chains: dict[str, list[int]] = (
            {}
        )  # cid -> [open_id, close_id, ...]
        self._stage_progression: list[int] = []  # event_ids of stage_update events

        # Build initial routing index
        self._rebuild_index()

        # Listen for new events
        eventlog.register_append_listener(self._on_event_appended)

    def _rebuild_index(self) -> None:
        """Rebuild routing index from event_index."""
        with self._lock:
            self._pointers.clear()
            self._kind_index.clear()
            self._content_terms.clear()
            self._identity_timeline.clear()
            self._commitment_chains.clear()
            self._stage_progression.clear()

            # Process all events from event_index
            for meta in self.event_index.index_scan():
                self._index_event_meta(meta)

    def _index_event_meta(self, meta) -> None:
        """Index a single event metadata for routing."""
        event_id = meta.event_id
        kind = meta.kind

        # Get content summary for semantic matching
        # For now, we'll fetch the actual event to get content
        # TODO: Store summaries in EventIndex to avoid fetches
        events = self.eventlog.read_by_ids([event_id])
        if not events:
            return

        event = events[0]
        content = str(event.get("content", ""))
        content_summary = content[:100]  # First 100 chars

        # Create pointer
        pointer = EventPointer(
            event_id=event_id, kind=kind, ts=meta.ts, content_summary=content_summary
        )

        self._pointers[event_id] = pointer

        # Update kind index
        if kind not in self._kind_index:
            self._kind_index[kind] = []
        self._kind_index[kind].append(event_id)

        # Extract content terms for semantic matching
        terms = self._extract_content_terms(content_summary)
        self._content_terms[event_id] = terms

        # Update structural indices
        self._update_structural_indices(event_id, kind, event)

    def _extract_content_terms(self, content: str) -> set[str]:
        """Extract searchable terms from content."""
        # Simple term extraction - split on whitespace and punctuation
        # Use basic string operations instead of regex per PMM guidelines
        words = (
            content.lower()
            .replace(",", " ")
            .replace(".", " ")
            .replace("!", " ")
            .replace("?", " ")
            .split()
        )
        terms = [
            word.strip(".,!?;:\"'()[]{}<>")
            for word in words
            if word.strip(".,!?;:\"'()[]{}<>")
        ]
        # Filter out very short terms and common words
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "this",
            "that",
            "these",
            "those",
        }
        return {term for term in terms if len(term) > 2 and term not in stopwords}

    def _update_structural_indices(
        self, event_id: int, kind: str, event: dict[str, Any]
    ) -> None:
        """Update structural relationship indices."""
        if kind == "identity_adopt":
            self._identity_timeline.append(event_id)
            # Keep timeline sorted by event_id
            self._identity_timeline.sort()

        elif kind == "stage_update":
            self._stage_progression.append(event_id)
            self._stage_progression.sort()

        elif kind in ("commitment_open", "commitment_close", "commitment_expire"):
            meta = event.get("meta", {})
            cid = meta.get("cid")
            if cid:
                if cid not in self._commitment_chains:
                    self._commitment_chains[cid] = []
                self._commitment_chains[cid].append(event_id)
                self._commitment_chains[cid].sort()

    def _on_event_appended(self, event: dict[str, Any]) -> None:
        """Handle new event appended to eventlog."""
        event_id = int(event.get("id", 0))
        if event_id <= 0:
            return

        # Get metadata from event_index
        meta = self.event_index.get_event_meta(event_id)
        if meta:
            self._index_event_meta(meta)

    def route(self, query: ContextQuery) -> list[int]:
        """Route a context query to relevant event IDs.

        Args:
            query: Context query specification

        Returns:
            List of event IDs ranked by relevance
        """
        with self._lock:
            candidates = []

            # Step 1: Collect required kinds (always include)
            for kind in query.required_kinds:
                if kind in self._kind_index:
                    for event_id in self._kind_index[kind]:
                        candidates.append(event_id)

            # Step 2: Semantic matching for additional candidates
            if query.semantic_terms:
                semantic_candidates = self._find_semantic_candidates(
                    query.semantic_terms
                )
                candidates.extend(semantic_candidates)

            # Step 3: Remove duplicates while preserving order
            seen = set()
            unique_candidates = []
            for event_id in candidates:
                if event_id not in seen:
                    seen.add(event_id)
                    unique_candidates.append(event_id)

            # Step 4: Score and rank candidates
            scored_candidates = []
            for event_id in unique_candidates:
                pointer = self._pointers.get(event_id)
                if pointer:
                    scored_pointer = self._score_candidate(pointer, query)
                    scored_candidates.append(scored_pointer)

            # Step 5: Sort by final score (descending)
            scored_candidates.sort(key=lambda p: p.final_score, reverse=True)

            # Step 6: Apply limit and return event IDs
            limited_candidates = scored_candidates[: query.limit]
            return [p.event_id for p in limited_candidates]

    def _find_semantic_candidates(self, terms: list[str]) -> list[int]:
        """Find events matching semantic terms."""
        candidates = []
        query_terms = {term.lower() for term in terms}

        for event_id, content_terms in self._content_terms.items():
            # Calculate term overlap
            overlap = len(query_terms & content_terms)
            if overlap > 0:
                candidates.append(event_id)

        return candidates

    def _score_candidate(
        self, pointer: EventPointer, query: ContextQuery
    ) -> EventPointer:
        """Score a candidate event for relevance."""
        # Semantic score based on term matching
        semantic_score = 0.0
        if query.semantic_terms:
            query_terms = {term.lower() for term in query.semantic_terms}
            content_terms = self._content_terms.get(pointer.event_id, set())
            overlap = len(query_terms & content_terms)
            semantic_score = overlap / len(query_terms) if query_terms else 0.0

        # Recency score based on event_id (higher ID = more recent)
        max_id = max(self._pointers.keys()) if self._pointers else 1
        recency_score = pointer.event_id / max_id

        # Final score combines semantic and recency
        final_score = (
            1.0 - query.recency_boost
        ) * semantic_score + query.recency_boost * recency_score

        return EventPointer(
            event_id=pointer.event_id,
            kind=pointer.kind,
            ts=pointer.ts,
            content_summary=pointer.content_summary,
            semantic_score=semantic_score,
            recency_score=recency_score,
            final_score=final_score,
        )

    # Structural query methods (preserved from original MemeGraph)

    def get_identity_timeline(self) -> list[int]:
        """Get chronological list of identity_adopt event IDs."""
        with self._lock:
            return list(self._identity_timeline)

    def get_latest_identity_event_id(self) -> int | None:
        """Get the most recent identity_adopt event ID."""
        with self._lock:
            return self._identity_timeline[-1] if self._identity_timeline else None

    def get_stage_progression(self) -> list[int]:
        """Get chronological list of stage_update event IDs."""
        with self._lock:
            return list(self._stage_progression)

    def get_commitment_chain(self, cid: str) -> list[int]:
        """Get event chain for a specific commitment ID."""
        with self._lock:
            return list(self._commitment_chains.get(cid, []))

    def get_stats(self) -> dict[str, Any]:
        """Get router statistics."""
        with self._lock:
            return {
                "indexed_events": len(self._pointers),
                "kinds_indexed": len(self._kind_index),
                "identity_events": len(self._identity_timeline),
                "stage_events": len(self._stage_progression),
                "commitment_chains": len(self._commitment_chains),
            }
