# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_autonomy_integration_phase2.py
"""Tests for Phase 2 autonomy integration (telemetry emission)."""


from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel


def test_emit_stability_metrics():
    """Test stability_metrics emission on first call."""
    log = EventLog(":memory:")
    log.append(kind="policy_update", content="change")
    log.append(kind="assistant_message", content="COMMIT: task")

    kernel = AutonomyKernel(log)
    initial_count = len(log.read_all())

    kernel._maybe_emit_stability_metrics()
    after_count = len(log.read_all())

    assert after_count == initial_count + 1
    events = log.read_all()
    stability_event = next(
        (e for e in events if e["kind"] == "stability_metrics"), None
    )
    assert stability_event is not None
    assert stability_event["meta"]["source"] == "autonomy_kernel"


def test_stability_metrics_idempotent():
    """Test stability_metrics not emitted when unchanged."""
    log = EventLog(":memory:")
    log.append(kind="policy_update", content="change")

    kernel = AutonomyKernel(log)
    kernel._maybe_emit_stability_metrics()
    count_after_first = len(log.read_all())

    kernel._maybe_emit_stability_metrics()  # Same ledger
    count_after_second = len(log.read_all())

    assert count_after_second == count_after_first


def test_emit_coherence_check():
    """Test coherence_check emission when enabled and claims exist."""
    log = EventLog(":memory:")
    log.append(
        kind="claim",
        content='CLAIM:memory={"domain": "memory", "value": "short"}',
    )

    kernel = AutonomyKernel(log)
    kernel._maybe_emit_coherence_check()
    events = log.read_all()

    coherence_event = next((e for e in events if e["kind"] == "coherence_check"), None)
    assert coherence_event is not None
    assert coherence_event["meta"]["source"] == "autonomy_kernel"


def test_coherence_check_disabled():
    """Test coherence_check not emitted when disabled."""
    log = EventLog(":memory:")
    log.append(
        kind="claim",
        content='CLAIM:memory={"domain": "memory", "value": "short"}',
    )

    kernel = AutonomyKernel(log)
    kernel._coherence_enabled = False
    initial_count = len(log.read_all())

    kernel._maybe_emit_coherence_check()
    after_count = len(log.read_all())

    assert after_count == initial_count


def test_stability_metrics_change_detection():
    """Test stability_metrics emitted when metrics change."""
    log = EventLog(":memory:")
    log.append(kind="policy_update", content="change")

    kernel = AutonomyKernel(log)
    kernel._maybe_emit_stability_metrics()
    events_after_first = log.read_all()
    metrics_after_first = [
        e for e in events_after_first if e["kind"] == "stability_metrics"
    ]

    log.append(kind="policy_update", content="another change")
    kernel._maybe_emit_stability_metrics()
    events_after_second = log.read_all()
    metrics_after_second = [
        e for e in events_after_second if e["kind"] == "stability_metrics"
    ]

    # One additional stability_metrics event should be emitted when metrics change
    assert len(metrics_after_second) == len(metrics_after_first) + 1


def test_no_extra_events_in_decide_next_action():
    """Test that decide_next_action does not mutate the log."""
    log = EventLog(":memory:")
    # Add enough events to trigger decision
    for i in range(20):
        log.append(kind="user_message", content=f"msg {i}")
    log.append(
        kind="reflection",
        content='{"intent": "test"}',
        meta={"source": "autonomy_kernel"},
    )

    kernel = AutonomyKernel(log)
    initial_count = len(log.read_all())

    kernel.decide_next_action()
    after_count = len(log.read_all())

    # decide_next_action must be side-effect free; telemetry is emitted via
    # explicit maintenance paths, not during decision itself.
    assert after_count == initial_count
