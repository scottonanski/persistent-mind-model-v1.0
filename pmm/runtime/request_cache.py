"""Request-scoped caching for performance optimization.

Provides a cache layer that lives for the duration of a single request,
eliminating redundant database reads while maintaining the ledger → mirror → memegraph
paradigm integrity.

Design Principles:
- Read-only: Never mutates the ledger
- Request-scoped: Cache cleared after each request
- Transparent: Drop-in replacement for eventlog.read_all()
- Deterministic: Same results as direct ledger access
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RequestCache:
    """Request-scoped cache for ledger data.

    Caches expensive operations within a single request to avoid redundant
    database reads. The cache is invalidated when new events are appended,
    ensuring consistency with the ledger → mirror → memegraph flow.

    Usage:
        cache = RequestCache(eventlog)
        events = cache.get_events()  # First call reads from DB
        events = cache.get_events()  # Subsequent calls use cache

        # After appending events, cache auto-invalidates
        eventlog.append(kind="user", content="...")
        events = cache.get_events()  # Reads from DB again
    """

    def __init__(self, eventlog):
        """Initialize request cache.

        Args:
            eventlog: EventLog instance to cache reads from
        """
        self.eventlog = eventlog
        self._events_cache: Optional[List[Dict[str, Any]]] = None
        self._identity_cache: Optional[Dict[str, Any]] = None
        self._self_model_cache: Optional[Dict[str, Any]] = None
        self._last_event_id: Optional[int] = None
        self._hit_count = 0
        self._miss_count = 0

    def get_events(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """Get all events from ledger with caching.

        Args:
            refresh: Force cache refresh even if valid

        Returns:
            List of event dictionaries
        """
        if refresh or not self._is_cache_valid():
            self._miss_count += 1
            self._events_cache = self.eventlog.read_all()
            self._update_last_event_id()
            logger.debug(
                f"RequestCache MISS: read_all() called (miss={self._miss_count})"
            )
        else:
            self._hit_count += 1
            logger.debug(
                f"RequestCache HIT: using cached events (hit={self._hit_count})"
            )

        return self._events_cache

    def get_tail(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get recent events from ledger.

        Note: This bypasses cache since tail queries are already optimized.

        Args:
            limit: Number of recent events to fetch

        Returns:
            List of recent event dictionaries
        """
        try:
            return self.eventlog.read_tail(limit=limit)
        except Exception:
            # Fallback to cached full read
            events = self.get_events()
            return events[-limit:] if events else []

    def get_identity(self) -> Dict[str, Any]:
        """Get identity projection with caching.

        Returns:
            Identity dictionary with name, traits, etc.
        """
        if self._identity_cache is None or not self._is_cache_valid():
            from pmm.storage.projection import build_identity

            events = self.get_events()
            self._identity_cache = build_identity(events)

        return self._identity_cache

    def get_self_model(self) -> Dict[str, Any]:
        """Get self-model projection with caching.

        Returns:
            Self-model dictionary
        """
        if self._self_model_cache is None or not self._is_cache_valid():
            from pmm.storage.projection import build_self_model

            events = self.get_events()
            self._self_model_cache = build_self_model(events, eventlog=self.eventlog)

        return self._self_model_cache

    def invalidate(self):
        """Invalidate all caches.

        Called automatically when events are appended to the ledger.
        """
        self._events_cache = None
        self._identity_cache = None
        self._self_model_cache = None
        self._last_event_id = None
        logger.debug("RequestCache invalidated")

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid.

        Cache is valid if:
        1. Cache exists
        2. No new events have been appended since cache was populated

        Returns:
            True if cache is valid, False otherwise
        """
        if self._events_cache is None:
            return False

        # Check if ledger has grown
        try:
            current_last_id = self._get_current_last_event_id()
            if current_last_id != self._last_event_id:
                logger.debug(
                    f"Cache invalid: last_id changed from {self._last_event_id} "
                    f"to {current_last_id}"
                )
                return False
        except Exception:
            # If we can't determine, assume invalid
            return False

        return True

    def _update_last_event_id(self):
        """Update the last event ID from cached events."""
        if self._events_cache:
            try:
                self._last_event_id = int(self._events_cache[-1].get("id", 0))
            except (IndexError, ValueError, TypeError):
                self._last_event_id = None

    def _get_current_last_event_id(self) -> Optional[int]:
        """Get the current last event ID from ledger without full read.

        Returns:
            Last event ID or None if ledger is empty
        """
        try:
            # Try to get just the last event
            tail = self.eventlog.read_tail(limit=1)
            if tail:
                return int(tail[-1].get("id", 0))
        except Exception:
            pass

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with hit/miss counts and hit rate
        """
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0.0

        return {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "total": total,
            "hit_rate": hit_rate,
            "cache_valid": self._is_cache_valid(),
        }

    def reset_stats(self):
        """Reset cache statistics."""
        self._hit_count = 0
        self._miss_count = 0


class CachedEventLog:
    """Wrapper around EventLog that provides request-scoped caching.

    This is a transparent wrapper that intercepts read operations and
    caches them within a request scope. Write operations (append) are
    passed through and invalidate the cache.

    Usage:
        cached_log = CachedEventLog(eventlog)
        events = cached_log.read_all()  # Cached
        cached_log.append(kind="user", content="...")  # Invalidates cache
        events = cached_log.read_all()  # Fresh read
    """

    def __init__(self, eventlog):
        """Initialize cached event log.

        Args:
            eventlog: EventLog instance to wrap
        """
        self._eventlog = eventlog
        self._cache = RequestCache(eventlog)

    def read_all(self) -> List[Dict[str, Any]]:
        """Read all events with caching."""
        return self._cache.get_events()

    def read_tail(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Read recent events (bypasses cache)."""
        return self._cache.get_tail(limit)

    def append(self, kind: str, content: str = "", meta: Optional[Dict] = None) -> int:
        """Append event and invalidate cache.

        Args:
            kind: Event kind
            content: Event content
            meta: Event metadata

        Returns:
            Event ID
        """
        # Invalidate cache before append
        self._cache.invalidate()

        # Pass through to underlying eventlog
        return self._eventlog.append(kind=kind, content=content, meta=meta)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.get_stats()

    def __getattr__(self, name):
        """Delegate all other methods to underlying eventlog."""
        return getattr(self._eventlog, name)
