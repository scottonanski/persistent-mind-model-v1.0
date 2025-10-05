#!/usr/bin/env python3
"""Performance profiling script for PMM after monolithic refactor.

Identifies bottlenecks in loop.py and tracker.py by:
1. Counting read_all() calls (major bottleneck)
2. Measuring projection rebuilds
3. Tracking snapshot cache hits/misses
4. Profiling key operations
"""

import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pmm.config import load as load_config
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.runtime.profiler import PerformanceProfiler
from pmm.storage.eventlog import EventLog


class InstrumentedEventLog:
    """Wrapper that counts read_all() calls."""

    def __init__(self, eventlog: EventLog):
        self._eventlog = eventlog
        self.read_all_count = 0
        self.read_tail_count = 0
        self.append_count = 0

    def read_all(self):
        self.read_all_count += 1
        return self._eventlog.read_all()

    def read_tail(self, limit: int = 100):
        self.read_tail_count += 1
        return self._eventlog.read_tail(limit=limit)

    def append(self, **kwargs):
        self.append_count += 1
        return self._eventlog.append(**kwargs)

    def __getattr__(self, name):
        """Forward all other methods to wrapped eventlog."""
        return getattr(self._eventlog, name)


def profile_snapshot_operations(
    runtime: Runtime, profiler: PerformanceProfiler
) -> dict[str, Any]:
    """Profile snapshot cache behavior."""
    results = {
        "cache_hits": 0,
        "cache_misses": 0,
        "snapshot_builds": 0,
    }

    # Test cache hit
    with profiler.measure("snapshot_first_access"):
        snapshot1 = runtime._get_snapshot()
    results["snapshot_builds"] += 1

    # Test cache hit (no new events)
    with profiler.measure("snapshot_cache_hit"):
        snapshot2 = runtime._get_snapshot()
    if snapshot1 is snapshot2:
        results["cache_hits"] += 1

    # Invalidate cache by appending event
    with profiler.measure("append_event"):
        runtime.eventlog.append(kind="test_event", content="test", meta={})

    # Test cache miss (new event)
    with profiler.measure("snapshot_cache_miss"):
        snapshot3 = runtime._get_snapshot()
    if snapshot3 is not snapshot2:
        results["cache_misses"] += 1
        results["snapshot_builds"] += 1

    return results


def profile_tracker_operations(
    runtime: Runtime, profiler: PerformanceProfiler
) -> dict[str, Any]:
    """Profile commitment tracker operations."""
    results = {
        "list_open_time_ms": 0,
        "add_commitment_time_ms": 0,
        "process_evidence_time_ms": 0,
    }

    tracker = runtime.tracker

    # Profile list_open_commitments
    with profiler.measure("tracker_list_open"):
        start = time.perf_counter()
        tracker.list_open_commitments()
        results["list_open_time_ms"] = (time.perf_counter() - start) * 1000

    # Profile add_commitment
    with profiler.measure("tracker_add_commitment"):
        start = time.perf_counter()
        tracker.add_commitment("Test commitment for profiling", source="test")
        results["add_commitment_time_ms"] = (time.perf_counter() - start) * 1000

    # Profile process_evidence
    with profiler.measure("tracker_process_evidence"):
        start = time.perf_counter()
        tracker.process_evidence("Done: completed the test")
        results["process_evidence_time_ms"] = (time.perf_counter() - start) * 1000

    return results


def profile_user_turn(
    runtime: Runtime, profiler: PerformanceProfiler
) -> dict[str, Any]:
    """Profile a complete user turn."""
    results = {
        "total_time_ms": 0,
        "context_build_ms": 0,
        "llm_time_ms": 0,
        "post_process_ms": 0,
    }

    with profiler.measure("user_turn_total"):
        start_total = time.perf_counter()

        try:
            # Simulate user input
            user_text = "What's the status of my commitments?"

            # This will trigger the full pipeline
            with profiler.measure("user_turn_handle"):
                runtime.handle_user(user_text)

            results["total_time_ms"] = (time.perf_counter() - start_total) * 1000
        except Exception as e:
            results["error"] = str(e)

    return results


def analyze_read_all_hotspots(instrumented_log: InstrumentedEventLog) -> dict[str, Any]:
    """Analyze read_all() call patterns."""
    return {
        "read_all_calls": instrumented_log.read_all_count,
        "read_tail_calls": instrumented_log.read_tail_count,
        "append_calls": instrumented_log.append_count,
        "read_all_per_append": (
            instrumented_log.read_all_count / instrumented_log.append_count
            if instrumented_log.append_count > 0
            else 0
        ),
    }


def main():
    """Run performance profiling."""
    print("=" * 80)
    print("PMM PERFORMANCE PROFILING - POST REFACTOR")
    print("=" * 80)
    print()

    # Initialize profiler
    profiler = PerformanceProfiler(enabled=True)

    # Load config
    with profiler.measure("config_load"):
        cfg_dict = load_config()
        llm_cfg = LLMConfig(
            provider=cfg_dict.get("provider", "anthropic"),
            model=cfg_dict.get("model", "claude-3-5-sonnet-20241022"),
            api_key=cfg_dict.get("api_key", ""),
        )

    # Create test database
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_perf.db"

        # Initialize eventlog
        with profiler.measure("eventlog_init"):
            base_eventlog = EventLog(str(db_path))

        # Wrap with instrumentation
        instrumented_log = InstrumentedEventLog(base_eventlog)

        # Initialize runtime
        with profiler.measure("runtime_init"):
            runtime = Runtime(llm_cfg, instrumented_log)

        print("## Baseline Metrics")
        print("-" * 80)

        # Add some baseline events
        with profiler.measure("baseline_events"):
            for i in range(50):
                instrumented_log.append(
                    kind="test_event", content=f"Test event {i}", meta={"index": i}
                )

        baseline = analyze_read_all_hotspots(instrumented_log)
        print(f"Baseline read_all() calls: {baseline['read_all_calls']}")
        print(f"Baseline append() calls: {baseline['append_calls']}")
        print()

        # Reset counters
        instrumented_log.read_all_count = 0
        instrumented_log.read_tail_count = 0
        instrumented_log.append_count = 0

        print("## Snapshot Cache Performance")
        print("-" * 80)
        snapshot_results = profile_snapshot_operations(runtime, profiler)
        print(f"Cache hits: {snapshot_results['cache_hits']}")
        print(f"Cache misses: {snapshot_results['cache_misses']}")
        print(f"Snapshot builds: {snapshot_results['snapshot_builds']}")
        print()

        print("## Tracker Performance")
        print("-" * 80)
        tracker_results = profile_tracker_operations(runtime, profiler)
        print(f"list_open_commitments: {tracker_results['list_open_time_ms']:.2f}ms")
        print(f"add_commitment: {tracker_results['add_commitment_time_ms']:.2f}ms")
        print(f"process_evidence: {tracker_results['process_evidence_time_ms']:.2f}ms")
        print()

        print("## Read Pattern Analysis")
        print("-" * 80)
        read_analysis = analyze_read_all_hotspots(instrumented_log)
        print(f"Total read_all() calls: {read_analysis['read_all_calls']}")
        print(f"Total read_tail() calls: {read_analysis['read_tail_calls']}")
        print(f"Total append() calls: {read_analysis['append_calls']}")
        print(f"read_all() per append: {read_analysis['read_all_per_append']:.2f}")
        print()

        # Get profiler report
        print("## Detailed Performance Report")
        print(profiler.get_report(sort_by="total_ms"))
        print()

        # Identify bottlenecks
        print("## IDENTIFIED BOTTLENECKS")
        print("=" * 80)

        bottlenecks = []

        if read_analysis["read_all_calls"] > 20:
            bottlenecks.append(
                {
                    "issue": "Excessive read_all() calls",
                    "count": read_analysis["read_all_calls"],
                    "impact": "HIGH",
                    "recommendation": "Implement request-scoped caching or pass events as parameters",
                }
            )

        if read_analysis["read_all_per_append"] > 5:
            bottlenecks.append(
                {
                    "issue": "High read_all() to append ratio",
                    "ratio": read_analysis["read_all_per_append"],
                    "impact": "HIGH",
                    "recommendation": "Cache events within operation scope, use read_tail() for recent data",
                }
            )

        if snapshot_results["cache_misses"] > snapshot_results["cache_hits"]:
            bottlenecks.append(
                {
                    "issue": "Poor snapshot cache hit rate",
                    "hit_rate": f"{snapshot_results['cache_hits']}/{snapshot_results['cache_hits'] + snapshot_results['cache_misses']}",
                    "impact": "MEDIUM",
                    "recommendation": "Review cache invalidation logic, consider longer cache lifetime",
                }
            )

        if bottlenecks:
            for i, bottleneck in enumerate(bottlenecks, 1):
                print(f"\n{i}. {bottleneck['issue']}")
                print(f"   Impact: {bottleneck['impact']}")
                if "count" in bottleneck:
                    print(f"   Count: {bottleneck['count']}")
                if "ratio" in bottleneck:
                    print(f"   Ratio: {bottleneck['ratio']:.2f}")
                if "hit_rate" in bottleneck:
                    print(f"   Hit Rate: {bottleneck['hit_rate']}")
                print(f"   Recommendation: {bottleneck['recommendation']}")
        else:
            print("No major bottlenecks detected!")

        print()
        print("=" * 80)
        print("PROFILING COMPLETE")
        print("=" * 80)


if __name__ == "__main__":
    main()
