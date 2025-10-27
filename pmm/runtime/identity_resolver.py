"""Identity resolver using verified events only.

Replaces parser-based identity resolution with verified ledger reads.
Prevents "What/Or/Not" parsing bugs by only accepting identity from
actual identity_adopt and identity_checkpoint events.

Design principles:
- Truth-first: Only verified events determine identity
- No parser auto-adoption: Classifier suggests only, cannot commit
- Full history: Uses router to access complete identity timeline
- Cached with TTL: Performance optimization with invalidation
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from pmm.runtime.event_router import ContextQuery, EventRouter
from pmm.storage.eventlog import EventLog

__all__ = ["IdentityResolver", "IdentityProposal", "ResolvedIdentity"]


@dataclass(frozen=True)
class IdentityProposal:
    """Identity candidate from classifier (suggestion only, cannot auto-adopt)."""

    name: str | None
    confidence: float = 0.0
    source: str = "classifier"

    def __post_init__(self):
        # Enforce confidence = 0.0 to prevent auto-adoption
        object.__setattr__(self, "confidence", 0.0)


@dataclass(frozen=True)
class ResolvedIdentity:
    """Verified identity from ledger events."""

    name: str
    event_id: int
    timestamp: str
    source: str
    confidence: float
    truth_source: str = "read"


class IdentityResolver:
    """Resolves identity from verified events only.

    Uses EventRouter to access full identity timeline and caches results
    with TTL for performance. Only identity_adopt and identity_checkpoint
    events can determine identity - parser suggestions are advisory only.
    """

    def __init__(self, eventlog: EventLog, event_router: EventRouter) -> None:
        self.eventlog = eventlog
        self.event_router = event_router
        self._lock = threading.RLock()

        # Cache with TTL
        self._cached_identity: ResolvedIdentity | None = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 30.0  # 30 second TTL

        # Listen for identity events to invalidate cache
        eventlog.register_append_listener(self._on_event_appended)

    def _on_event_appended(self, event: dict[str, Any]) -> None:
        """Invalidate cache when identity events are added."""
        kind = event.get("kind", "")
        if kind in ("identity_adopt", "identity_checkpoint"):
            with self._lock:
                self._cached_identity = None
                self._cache_timestamp = 0.0

    def current_identity(self) -> ResolvedIdentity | None:
        """Get current verified identity from ledger events.

        Returns the most recent identity_adopt or identity_checkpoint event,
        or None if no identity has been established.

        Results are cached with TTL for performance.
        """
        with self._lock:
            now = time.time()

            # Check cache validity
            if (
                self._cached_identity is not None
                and now - self._cache_timestamp < self._cache_ttl
            ):
                return self._cached_identity

            # Route for identity events (full history, no recency bias for accuracy)
            identity_query = ContextQuery(
                required_kinds=["identity_adopt", "identity_checkpoint"],
                semantic_terms=[],
                limit=50,  # Get enough to find the latest
                recency_boost=0.0,  # No bias - want chronological accuracy
            )

            identity_event_ids = self.event_router.route(identity_query)
            if not identity_event_ids:
                self._cached_identity = None
                self._cache_timestamp = now
                return None

            # Fetch actual events and find the most recent
            identity_events = self.eventlog.read_by_ids(
                identity_event_ids, verify_hash=False
            )
            if not identity_events:
                self._cached_identity = None
                self._cache_timestamp = now
                return None

            # Sort by timestamp to get the most recent
            identity_events.sort(key=lambda e: (e.get("ts", ""), int(e.get("id", 0))))
            latest_event = identity_events[-1]

            # Extract identity information
            name = str(latest_event.get("content", "Unknown"))
            event_id = int(latest_event.get("id", 0))
            timestamp = str(latest_event.get("ts", ""))
            meta = latest_event.get("meta", {})
            source = str(meta.get("source", "unknown"))
            confidence = float(meta.get("confidence", 0.0))

            # Create resolved identity
            resolved = ResolvedIdentity(
                name=name,
                event_id=event_id,
                timestamp=timestamp,
                source=source,
                confidence=confidence,
                truth_source="read",
            )

            # Cache the result
            self._cached_identity = resolved
            self._cache_timestamp = now

            return resolved

    def get_identity_timeline(self) -> list[ResolvedIdentity]:
        """Get complete identity timeline from verified events.

        Returns all identity changes in chronological order.
        Useful for debugging identity drift issues.
        """
        # Route for all identity events
        identity_query = ContextQuery(
            required_kinds=["identity_adopt", "identity_checkpoint"],
            semantic_terms=[],
            limit=100,  # Get complete history
            recency_boost=0.0,  # Chronological order
        )

        identity_event_ids = self.event_router.route(identity_query)
        if not identity_event_ids:
            return []

        # Fetch and sort events chronologically
        identity_events = self.eventlog.read_by_ids(
            identity_event_ids, verify_hash=False
        )
        identity_events.sort(key=lambda e: (e.get("ts", ""), int(e.get("id", 0))))

        # Convert to ResolvedIdentity objects
        timeline = []
        for event in identity_events:
            name = str(event.get("content", "Unknown"))
            event_id = int(event.get("id", 0))
            timestamp = str(event.get("ts", ""))
            meta = event.get("meta", {})
            source = str(meta.get("source", "unknown"))
            confidence = float(meta.get("confidence", 0.0))

            resolved = ResolvedIdentity(
                name=name,
                event_id=event_id,
                timestamp=timestamp,
                source=source,
                confidence=confidence,
                truth_source="read",
            )
            timeline.append(resolved)

        return timeline

    def propose_identity(self, text: str) -> IdentityProposal:
        """Generate identity proposal from text (advisory only).

        This replaces the old classifier auto-adoption behavior.
        Proposals have confidence=0.0 and cannot trigger adoption.

        Args:
            text: Input text to analyze

        Returns:
            IdentityProposal with confidence=0.0 (advisory only)
        """
        if not text or not text.strip():
            return IdentityProposal(name=None, confidence=0.0)

        # Stoplist for interrogative/conjunction words
        stoplist = {
            "what",
            "who",
            "why",
            "how",
            "when",
            "where",
            "or",
            "and",
            "not",
            "but",
            "if",
            "then",
            "yes",
            "no",
            "maybe",
            "perhaps",
            "might",
        }

        # Simple extraction - look for capitalized words
        words = text.strip().split()
        candidates = []

        for word in words:
            # Skip first word (sentence capitalization)
            if word == words[0]:
                continue

            # Clean punctuation
            clean_word = word.strip(".,!?;:\"'()[]{}<>").lower()

            # Skip stoplist words
            if clean_word in stoplist:
                continue

            # Look for capitalized words (potential names)
            if len(word) > 1 and word[0].isupper() and clean_word.isalpha():
                candidates.append(word.strip(".,!?;:\"'()[]{}<>"))

        # Return first candidate or None
        candidate_name = candidates[0] if candidates else None

        return IdentityProposal(
            name=candidate_name,
            confidence=0.0,  # Always 0.0 - cannot auto-adopt
            source="classifier",
        )

    def adopt_identity(
        self,
        name: str,
        *,
        source: str = "system",
        intent: str = "explicit_adoption",
        confidence: float = 1.0,
    ) -> int:
        """Controlled identity adoption entrypoint.

        This is the ONLY way to change identity. Requires explicit intent
        signals, not free-text parsing.

        Args:
            name: New identity name
            source: Source of adoption (system/user/admin)
            intent: Explicit intent signal
            confidence: Confidence level (0.0-1.0)

        Returns:
            Event ID of the created identity_adopt event
        """
        if not name or not name.strip():
            raise ValueError("Identity name cannot be empty")

        if source not in ("system", "user", "admin"):
            raise ValueError(f"Invalid source: {source}")

        # Sanitize name
        sanitized_name = name.strip()

        # Create identity_adopt event
        event_id = self.eventlog.append(
            kind="identity_adopt",
            content=sanitized_name,
            meta={
                "name": sanitized_name,
                "sanitized": sanitized_name,
                "source": source,
                "intent": intent,
                "confidence": float(confidence),
                "stable_window": True,
            },
        )

        # Cache will be invalidated by the event listener
        return event_id

    def get_stats(self) -> dict[str, Any]:
        """Get resolver statistics for monitoring."""
        with self._lock:
            current = self.current_identity()
            timeline = self.get_identity_timeline()

            return {
                "current_identity": current.name if current else None,
                "current_event_id": current.event_id if current else None,
                "total_identity_changes": len(timeline),
                "cache_valid": self._cached_identity is not None,
                "cache_age_seconds": time.time() - self._cache_timestamp,
            }
