"""Performance profiling utilities for PMM runtime.

Provides lightweight profiling to measure and track performance of key operations
without impacting production performance.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProfileEntry:
    """Single profiling measurement."""

    label: str
    duration_ms: float
    timestamp: float


@dataclass
class PerformanceProfile:
    """Aggregated performance statistics for a label."""

    label: str
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    measurements: list[float] = field(default_factory=list)

    @property
    def avg_ms(self) -> float:
        """Average duration in milliseconds."""
        return self.total_ms / self.count if self.count > 0 else 0.0

    @property
    def p50_ms(self) -> float:
        """Median duration in milliseconds."""
        if not self.measurements:
            return 0.0
        sorted_vals = sorted(self.measurements)
        mid = len(sorted_vals) // 2
        return sorted_vals[mid]

    @property
    def p95_ms(self) -> float:
        """95th percentile duration in milliseconds."""
        if not self.measurements:
            return 0.0
        sorted_vals = sorted(self.measurements)
        idx = int(len(sorted_vals) * 0.95)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def add_measurement(self, duration_ms: float):
        """Add a new measurement."""
        self.count += 1
        self.total_ms += duration_ms
        self.min_ms = min(self.min_ms, duration_ms)
        self.max_ms = max(self.max_ms, duration_ms)
        self.measurements.append(duration_ms)

        # Keep only last 1000 measurements to avoid memory bloat
        if len(self.measurements) > 1000:
            self.measurements = self.measurements[-1000:]


class PerformanceProfiler:
    """Lightweight performance profiler for PMM operations.

    Usage:
        profiler = PerformanceProfiler()

        with profiler.measure("database_read"):
            events = eventlog.read_all()

        with profiler.measure("llm_inference"):
            reply = chat.generate(messages)

        # Get report
        report = profiler.get_report()
        print(report)

        # Or get structured data
        stats = profiler.get_stats()
    """

    def __init__(self, enabled: bool = True):
        """Initialize profiler.

        Args:
            enabled: If False, profiling is disabled (zero overhead)
        """
        self.enabled = enabled
        self._profiles: dict[str, PerformanceProfile] = {}
        self._entries: list[ProfileEntry] = []
        self._session_start = time.time()

    @contextmanager
    def measure(self, label: str):
        """Context manager to measure duration of a code block.

        Args:
            label: Name for this measurement

        Yields:
            None
        """
        if not self.enabled:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._record(label, elapsed_ms)

    def _record(self, label: str, duration_ms: float):
        """Record a measurement."""
        # Add to profile
        if label not in self._profiles:
            self._profiles[label] = PerformanceProfile(label=label)

        self._profiles[label].add_measurement(duration_ms)

        # Add to entries
        entry = ProfileEntry(
            label=label, duration_ms=duration_ms, timestamp=time.time()
        )
        self._entries.append(entry)

        # Keep only last 10000 entries
        if len(self._entries) > 10000:
            self._entries = self._entries[-10000:]

        # Log slow operations
        if duration_ms > 1000:  # > 1 second
            logger.warning(f"Slow operation: {label} took {duration_ms:.0f}ms")

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """Get structured performance statistics.

        Returns:
            Dictionary mapping label to statistics
        """
        return {
            label: {
                "count": profile.count,
                "total_ms": round(profile.total_ms, 2),
                "avg_ms": round(profile.avg_ms, 2),
                "min_ms": round(profile.min_ms, 2),
                "max_ms": round(profile.max_ms, 2),
                "p50_ms": round(profile.p50_ms, 2),
                "p95_ms": round(profile.p95_ms, 2),
            }
            for label, profile in self._profiles.items()
        }

    def get_report(self, sort_by: str = "total_ms") -> str:
        """Get human-readable performance report.

        Args:
            sort_by: Sort key (total_ms, avg_ms, count, max_ms)

        Returns:
            Formatted report string
        """
        if not self._profiles:
            return "No profiling data collected"

        # Sort profiles
        profiles = list(self._profiles.values())
        if sort_by == "total_ms":
            profiles.sort(key=lambda p: p.total_ms, reverse=True)
        elif sort_by == "avg_ms":
            profiles.sort(key=lambda p: p.avg_ms, reverse=True)
        elif sort_by == "count":
            profiles.sort(key=lambda p: p.count, reverse=True)
        elif sort_by == "max_ms":
            profiles.sort(key=lambda p: p.max_ms, reverse=True)

        # Build report
        lines = ["=" * 80]
        lines.append("PERFORMANCE PROFILE REPORT")
        lines.append("=" * 80)
        lines.append(
            f"{'Operation':<30} {'Count':>8} {'Total':>10} {'Avg':>10} {'Min':>10} {'Max':>10} {'P95':>10}"
        )
        lines.append("-" * 80)

        for profile in profiles:
            lines.append(
                f"{profile.label:<30} "
                f"{profile.count:>8} "
                f"{profile.total_ms:>9.1f}ms "
                f"{profile.avg_ms:>9.1f}ms "
                f"{profile.min_ms:>9.1f}ms "
                f"{profile.max_ms:>9.1f}ms "
                f"{profile.p95_ms:>9.1f}ms"
            )

        lines.append("=" * 80)

        # Add session summary
        session_duration = time.time() - self._session_start
        total_measured = sum(p.total_ms for p in profiles) / 1000  # Convert to seconds
        overhead_pct = (
            (total_measured / session_duration * 100) if session_duration > 0 else 0
        )

        lines.append(f"Session duration: {session_duration:.1f}s")
        lines.append(
            f"Total measured time: {total_measured:.1f}s ({overhead_pct:.1f}% of session)"
        )
        lines.append(f"Total operations: {sum(p.count for p in profiles)}")

        return "\n".join(lines)

    def reset(self):
        """Reset all profiling data."""
        self._profiles.clear()
        self._entries.clear()
        self._session_start = time.time()
        logger.debug("Profiler reset")

    def get_recent_entries(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent profiling entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of entry dictionaries
        """
        entries = self._entries[-limit:]
        return [
            {
                "label": entry.label,
                "duration_ms": round(entry.duration_ms, 2),
                "timestamp": entry.timestamp,
            }
            for entry in entries
        ]

    def export_to_trace_event(self, eventlog) -> int | None:
        """Export profiling data to eventlog as performance_trace event.

        Args:
            eventlog: EventLog instance to append to

        Returns:
            Event ID or None if export failed
        """
        if not self._profiles:
            return None

        try:
            stats = self.get_stats()
            return eventlog.append(
                kind="performance_trace",
                content="",
                meta={
                    "stats": stats,
                    "session_duration_s": round(time.time() - self._session_start, 2),
                    "total_operations": sum(p.count for p in self._profiles.values()),
                },
            )
        except Exception:
            logger.exception("Failed to export profiling data to eventlog")
            return None


# Global profiler instance (disabled by default)
_global_profiler: PerformanceProfiler | None = None


def get_global_profiler() -> PerformanceProfiler:
    """Get or create global profiler instance.

    Profiling is always enabled by default as it has minimal overhead (<5ms)
    and provides valuable performance insights.

    Returns:
        Global profiler instance
    """
    global _global_profiler
    if _global_profiler is None:
        # Always enabled - profiling is lightweight and provides valuable data
        _global_profiler = PerformanceProfiler(enabled=True)

    return _global_profiler


def enable_profiling():
    """Enable global profiling."""
    global _global_profiler
    _global_profiler = PerformanceProfiler(enabled=True)
    logger.info("Performance profiling enabled")


def disable_profiling():
    """Disable global profiling."""
    global _global_profiler
    if _global_profiler:
        _global_profiler.enabled = False
    logger.info("Performance profiling disabled")


def reset_profiling():
    """Reset global profiling data."""
    global _global_profiler
    if _global_profiler:
        _global_profiler.reset()
