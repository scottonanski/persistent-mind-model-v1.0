# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_autonomy_integration_phase1.py
"""Tests for Phase 1 autonomy integration (read-only wiring)."""


from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel


def test_autonomy_kernel_initializes_subsystems():
    """Test that AutonomyKernel initializes new subsystems without errors."""
    log = EventLog(":memory:")
    log.append(kind="user_message", content="Hello")
    log.append(
        kind="assistant_message",
        content="Hi\nCOMMIT: task",
        meta={"context": {"thread_id": "t1"}},
    )

    kernel = AutonomyKernel(log)

    # Check subsystems initialized
    assert hasattr(kernel, "context_graph")
    assert hasattr(kernel, "_stability_window")
    assert hasattr(kernel, "_coherence_enabled")
    assert kernel._stability_window == 100
    assert kernel._coherence_enabled is True

    # ContextGraph should have processed events
    assert kernel.context_graph.get_thread_events("t1") == [2]


def test_current_stability_metrics():
    """Test stability metrics helper."""
    log = EventLog(":memory:")
    log.append(kind="policy_update", content="Change")
    log.append(kind="assistant_message", content="COMMIT: task")

    kernel = AutonomyKernel(log)
    metrics = kernel._current_stability_metrics()

    assert "stability_score" in metrics
    assert metrics["window_size"] == 100
    # Deterministic: same inputs same output
    metrics2 = kernel._current_stability_metrics()
    assert metrics == metrics2


def test_current_coherence_view():
    """Test coherence view helper."""
    log = EventLog(":memory:")
    log.append(
        kind="claim",
        content='CLAIM:memory={"domain": "memory", "value": "short"}',
    )
    log.append(
        kind="claim",
        content='CLAIM:memory={"domain": "memory", "value": "long"}',
    )

    kernel = AutonomyKernel(log)
    claims, conflicts, score = kernel._current_coherence_view()

    assert len(claims) == 2
    assert len(conflicts) == 1
    assert score < 1.0  # Conflicts reduce score


def test_no_new_events_on_initialization():
    """Test that initializing kernel only emits expected config events."""
    log = EventLog(":memory:")
    initial_count = len(log.read_all())

    AutonomyKernel(log)
    events = log.read_all()
    # Kernel may append policy/retrieval config events, but nothing else.
    assert len(events) >= initial_count
    assert all(e["kind"] == "config" for e in events)


def test_no_new_events_on_helpers():
    """Test that calling helpers doesn't emit events."""
    log = EventLog(":memory:")
    log.append(kind="user_message", content="Test")

    kernel = AutonomyKernel(log)
    initial_count = len(log.read_all())

    kernel._current_stability_metrics()
    kernel._current_coherence_view()
    after_count = len(log.read_all())

    assert after_count == initial_count
