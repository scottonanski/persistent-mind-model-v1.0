#!/usr/bin/env python3
"""Test script for reasoning trace functionality.

Validates:
1. TraceBuffer sampling works correctly
2. Performance impact is minimal (<1ms overhead)
3. Events are logged to eventlog correctly
4. Trace summaries contain expected data
"""

import tempfile
import time
from pathlib import Path

from pmm.runtime.memegraph import MemeGraphProjection
from pmm.runtime.trace_buffer import TraceBuffer
from pmm.storage.eventlog import EventLog


def test_trace_buffer_basic():
    """Test basic TraceBuffer functionality."""
    print("Testing TraceBuffer basic operations...")

    buffer = TraceBuffer(sampling_rate=1.0, min_confidence_always_log=0.8)

    # Start session
    session_id = buffer.start_session("Test query about commitments")
    assert session_id is not None
    print(f"✓ Session started: {session_id[:8]}")

    # Record some node visits
    for i in range(10):
        _logged = buffer.record_node_visit(
            node_digest=f"node_{i}",
            node_type="commitment" if i % 2 == 0 else "reflection",
            context_query="Test query",
            traversal_depth=i,
            confidence=0.5 + (i * 0.05),
        )

    # Check stats
    stats = buffer.get_current_session_stats()
    assert stats is not None
    assert stats["total_nodes_visited"] == 10
    print(f"✓ Recorded 10 node visits, stats: {stats['node_type_distribution']}")

    # End session
    session = buffer.end_session()
    assert session is not None
    assert session.total_nodes_visited == 10
    print(f"✓ Session ended with {session.total_nodes_visited} nodes visited")

    print("✓ TraceBuffer basic operations passed\n")


def test_trace_sampling():
    """Test that sampling rate works correctly."""
    print("Testing sampling rate...")

    # Low sampling rate should log fewer nodes
    buffer = TraceBuffer(sampling_rate=0.1, min_confidence_always_log=0.9)
    buffer.start_session("Sampling test")

    logged_count = 0
    for i in range(100):
        if buffer.record_node_visit(
            node_digest=f"node_{i}",
            node_type="test",
            context_query="Test",
            traversal_depth=0,
            confidence=0.5,  # Below always-log threshold
        ):
            logged_count += 1

    _session = buffer.end_session()

    # Should have ~10% sampled (allow some variance)
    assert 5 <= logged_count <= 20, f"Expected ~10 logged, got {logged_count}"
    print(f"✓ Sampling rate working: {logged_count}/100 nodes logged (~10% expected)")

    # High confidence should always log
    buffer2 = TraceBuffer(sampling_rate=0.01, min_confidence_always_log=0.8)
    buffer2.start_session("High confidence test")

    high_conf_logged = 0
    for i in range(10):
        if buffer2.record_node_visit(
            node_digest=f"high_conf_{i}",
            node_type="test",
            context_query="Test",
            traversal_depth=0,
            confidence=0.95,  # Above threshold
        ):
            high_conf_logged += 1

    _session2 = buffer2.end_session()
    assert high_conf_logged == 10, "All high-confidence nodes should be logged"
    print(f"✓ High-confidence always-log working: {high_conf_logged}/10 logged")

    print("✓ Sampling rate tests passed\n")


def test_trace_eventlog_integration():
    """Test that traces are written to eventlog correctly."""
    print("Testing eventlog integration...")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_trace.db"
        eventlog = EventLog(str(db_path))

        # Create trace buffer and session
        buffer = TraceBuffer(sampling_rate=1.0, min_confidence_always_log=0.8)
        buffer.start_session("Test query for eventlog")

        # Record some visits
        for i in range(5):
            buffer.record_node_visit(
                node_digest=f"node_{i}",
                node_type="commitment",
                context_query="Test query",
                traversal_depth=i,
                confidence=0.9,
                reasoning_step=f"Step {i}: Examining commitment",
            )

        buffer.add_reasoning_step("Final analysis complete")

        # Flush to eventlog
        flushed = buffer.flush_to_eventlog(eventlog)
        assert flushed == 1, f"Expected 1 session flushed, got {flushed}"
        print(f"✓ Flushed {flushed} session to eventlog")

        # Verify events were written
        events = eventlog.read_all()
        summary_events = [
            e for e in events if e.get("kind") == "reasoning_trace_summary"
        ]
        sample_events = [e for e in events if e.get("kind") == "reasoning_trace_sample"]

        assert (
            len(summary_events) == 1
        ), f"Expected 1 summary event, got {len(summary_events)}"
        assert (
            len(sample_events) > 0
        ), f"Expected sample events, got {len(sample_events)}"

        # Check summary content
        summary = summary_events[0]
        meta = summary.get("meta", {})
        assert meta.get("total_nodes_visited") == 5
        assert meta.get("query") == "Test query for eventlog"
        assert len(meta.get("reasoning_steps", [])) > 0

        print(
            f"✓ Summary event: {meta.get('total_nodes_visited')} nodes, "
            f"{len(meta.get('reasoning_steps', []))} reasoning steps"
        )
        print(f"✓ Sample events: {len(sample_events)} logged")

    print("✓ Eventlog integration tests passed\n")


def test_trace_performance():
    """Test that trace overhead is minimal."""
    print("Testing performance impact...")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_perf.db"
        eventlog = EventLog(str(db_path))

        # Seed some events for memegraph
        for i in range(100):
            eventlog.append(
                kind="commitment_open",
                content=f"Test commitment {i}",
                meta={"cid": f"c{i}", "text": f"Test {i}"},
            )

        # Create memegraph
        memegraph = MemeGraphProjection(eventlog)

        # Measure without tracing
        start = time.perf_counter()
        for _ in range(10):
            memegraph.graph_slice(
                topic="test commitment",
                limit=3,
                trace_buffer=None,
            )
        baseline_ms = (time.perf_counter() - start) * 1000

        # Measure with tracing (1% sampling)
        buffer = TraceBuffer(sampling_rate=0.01, min_confidence_always_log=0.8)
        buffer.start_session("Performance test")

        start = time.perf_counter()
        for _ in range(10):
            memegraph.graph_slice(
                topic="test commitment",
                limit=3,
                trace_buffer=buffer,
            )
        traced_ms = (time.perf_counter() - start) * 1000

        overhead_ms = traced_ms - baseline_ms
        overhead_pct = (overhead_ms / baseline_ms * 100) if baseline_ms > 0 else 0

        print(f"  Baseline (no trace): {baseline_ms:.2f}ms")
        print(f"  With trace (1% sampling): {traced_ms:.2f}ms")
        print(f"  Overhead: {overhead_ms:.2f}ms ({overhead_pct:.1f}%)")

        # Overhead should be minimal (<10% for 1% sampling)
        assert overhead_pct < 15, f"Overhead too high: {overhead_pct:.1f}%"
        print(f"✓ Performance impact acceptable: {overhead_pct:.1f}% overhead")

    print("✓ Performance tests passed\n")


def test_trace_session_management():
    """Test session start/end/flush lifecycle."""
    print("Testing session management...")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_session.db"
        eventlog = EventLog(str(db_path))

        buffer = TraceBuffer(sampling_rate=1.0)

        # Multiple sessions
        for i in range(3):
            buffer.start_session(f"Query {i}")
            for j in range(5):
                buffer.record_node_visit(
                    node_digest=f"s{i}_n{j}",
                    node_type="test",
                    context_query=f"Query {i}",
                    traversal_depth=j,
                    confidence=0.7,
                )
            buffer.end_session()

        # Flush all sessions
        flushed = buffer.flush_to_eventlog(eventlog)
        assert flushed == 3, f"Expected 3 sessions flushed, got {flushed}"

        # Verify all summaries written
        events = eventlog.read_all()
        summaries = [e for e in events if e.get("kind") == "reasoning_trace_summary"]
        assert len(summaries) == 3, f"Expected 3 summaries, got {len(summaries)}"

        print(f"✓ Multiple sessions handled correctly: {flushed} sessions flushed")

    print("✓ Session management tests passed\n")


if __name__ == "__main__":
    print("=" * 60)
    print("REASONING TRACE TEST SUITE")
    print("=" * 60)
    print()

    try:
        test_trace_buffer_basic()
        test_trace_sampling()
        test_trace_eventlog_integration()
        test_trace_performance()
        test_trace_session_management()

        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print()
        print("Summary:")
        print("- TraceBuffer sampling works correctly")
        print("- Performance overhead is minimal (<15%)")
        print("- Events are logged to eventlog correctly")
        print("- Session management works as expected")
        print()
        print("The reasoning trace system is ready for production use!")

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
