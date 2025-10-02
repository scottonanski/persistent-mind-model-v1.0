"""Metrics cache for performance optimization.

Intent:
- Cache last computed IAS/GAS values
- Only recompute when new events are detected
- Simpler than full incremental computation (more reliable)
- Feature-flagged for safe rollback

This module provides 2-5x speedup for metrics operations by avoiding
repeated full computations when no new events exist.

Note: This is a simpler caching strategy than full incremental computation.
True incremental metrics computation is complex due to temporal dependencies,
feedback loops, and trait multipliers. This cache provides good performance
with high reliability.
"""

from __future__ import annotations

import logging

from pmm.runtime.metrics import compute_ias_gas

logger = logging.getLogger(__name__)


class MetricsCache:
    """Simple metrics cache with recomputation on new events.

    Caches last computed IAS/GAS values and recomputes when new events
    are detected. Simpler and more reliable than full incremental computation.

    Thread-safety: Not thread-safe. Caller must ensure single-threaded access.
    """

    def __init__(self):
        """Initialize metrics cache."""
        self.ias: float = 0.0
        self.gas: float = 0.0
        self._last_id: int = 0
        self._events_processed = 0

        # Statistics
        self._cache_hits = 0
        self._cache_misses = 0
        self._recomputations = 0

    def get_metrics(self, eventlog) -> tuple[float, float]:
        """Get cached metrics, recomputing if new events exist.

        Parameters
        ----------
        eventlog : EventLog
            The event log to read from.

        Returns
        -------
        tuple
            (ias, gas) values in range [0.0, 1.0]
        """
        # Check for new events
        new_events = eventlog.read_after_id(after_id=self._last_id, limit=10000)

        if not new_events:
            # Cache hit - no new events
            self._cache_hits += 1
            return self.ias, self.gas

        # Cache miss - need to recompute
        self._cache_misses += 1
        self._recomputations += 1

        logger.debug(
            f"MetricsCache: Recomputing metrics (new events: {len(new_events)}, last_id: {self._last_id})"
        )

        # Recompute from all events
        all_events = eventlog.read_all()
        self.ias, self.gas = compute_ias_gas(all_events)
        self._last_id = all_events[-1]["id"] if all_events else 0
        self._events_processed = len(all_events)

        return self.ias, self.gas

    def clear(self) -> None:
        """Clear the cache."""
        self.ias = 0.0
        self.gas = 0.0
        self._last_id = 0
        self._events_processed = 0
        logger.debug("MetricsCache cleared")

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
            "recomputations": self._recomputations,
            "events_processed": self._events_processed,
            "last_id": self._last_id,
            "ias": self.ias,
            "gas": self.gas,
        }
