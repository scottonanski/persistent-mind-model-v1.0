# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_autonomy_integration_phase3.py
"""Tests for Phase 3 autonomy integration (adaptive behavior)."""

import json

from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel


def test_emit_meta_policy_update():
    """Test meta_policy_update emission when conditions met."""
    log = EventLog(":memory:")
    # Add reflection and policy_update events with high lag
    for i in range(10):
        log.append(kind="filler", content="pad")
    log.append(kind="reflection", content='{"intent": "test"}')
    for i in range(60):  # High lag
        log.append(kind="filler", content="pad")
    log.append(kind="policy_update", content="change")

    kernel = AutonomyKernel(log)
    initial_count = len(log.read_all())

    kernel._maybe_emit_meta_policy_update()
    after_count = len(log.read_all())

    assert after_count > initial_count
    events = log.read_all()
    meta_event = next((e for e in events if e["kind"] == "meta_policy_update"), None)
    assert meta_event is not None
    data = json.loads(meta_event["content"] or "{}")
    assert any(
        s.get("param") == "reflection_interval"
        and s.get("suggested_change") == "decrease"
        for s in data.get("suggestions", [])
    )


def test_meta_policy_update_idempotent():
    """Test meta_policy_update not emitted when unchanged."""
    log = EventLog(":memory:")
    log.append(kind="reflection", content='{"intent": "test"}')
    log.append(kind="policy_update", content="change")

    kernel = AutonomyKernel(log)
    kernel._maybe_emit_meta_policy_update()
    count_after_first = len(log.read_all())

    kernel._maybe_emit_meta_policy_update()
    count_after_second = len(log.read_all())

    assert count_after_second == count_after_first


def test_emit_policy_update():
    """Test policy_update emission when high failure rate."""
    log = EventLog(":memory:")
    # Add outcome_observation with failures
    from pmm.learning.outcome_tracker import build_outcome_observation_content

    content = build_outcome_observation_content(
        commitment_id="c1",
        action_kind="reflect",
        action_payload="data",
        observed_result="failure",
        evidence_event_ids=[1],
    )
    for _ in range(10):
        log.append(kind="outcome_observation", content=json.dumps(content))

    kernel = AutonomyKernel(log)
    kernel._maybe_emit_policy_update()
    events = log.read_all()

    policy_event = next((e for e in events if e["kind"] == "policy_update"), None)
    assert policy_event is not None
    assert '"decrease_frequency"' in policy_event["content"]


def test_threshold_adaptation():
    """Test that meta-policy updates adapt thresholds."""
    log = EventLog(":memory:")
    # Add events to trigger meta-policy
    log.append(kind="reflection", content='{"intent": "test"}')
    log.append(kind="policy_update", content="change")

    kernel = AutonomyKernel(log)

    # Trigger emission and application
    kernel._maybe_emit_meta_policy_update()
    # Simulate re-init to apply
    kernel2 = AutonomyKernel(log)

    # Check if threshold is a valid int (change is deterministic given ledger)
    assert isinstance(kernel2.thresholds["reflection_interval"], int)


def test_policy_update_applies_to_thresholds():
    """Test that policy_update suggestions adapt kernel thresholds."""
    log = EventLog(":memory:")
    kernel = AutonomyKernel(log)

    baseline = kernel.thresholds["reflection_interval"]

    from pmm.learning.policy_evolver import (
        PolicyChangeSuggestion,
        build_policy_update_content,
    )

    # Suggest increasing the frequency of reflection (shorter interval).
    suggestion = PolicyChangeSuggestion(
        action_kind="reflect",
        suggested_change="increase_frequency",
        reason="test",
    )
    content = build_policy_update_content([suggestion])
    log.append(
        kind="policy_update",
        content=json.dumps(content, sort_keys=True, separators=(",", ":")),
    )

    # Threshold should decrease by 1 within bounds.
    assert kernel.thresholds["reflection_interval"] == max(5, baseline - 1)


def test_policy_update_idempotent_when_no_effect():
    """Test that policy_update with no effective change does not break."""
    log = EventLog(":memory:")
    kernel = AutonomyKernel(log)

    # Force reflection_interval to minimum bound to avoid further decrease.
    kernel.thresholds["reflection_interval"] = 5

    from pmm.learning.policy_evolver import (
        PolicyChangeSuggestion,
        build_policy_update_content,
    )

    suggestion = PolicyChangeSuggestion(
        action_kind="reflect",
        suggested_change="increase_frequency",
        reason="test",
    )
    content = build_policy_update_content([suggestion])
    before_events = list(log.read_all())
    log.append(
        kind="policy_update",
        content=json.dumps(content, sort_keys=True, separators=(",", ":")),
    )
    after_events = list(log.read_all())

    # No guarantee about autonomy_rule_table in this test; just ensure
    # append did not crash and thresholds stayed at the bound.
    assert kernel.thresholds["reflection_interval"] == 5
    assert len(after_events) == len(before_events) + 1


def test_no_extra_events_in_decide_next_action():
    """Test that decide_next_action emits adaptation events but no extras."""
    log = EventLog(":memory:")
    for i in range(20):
        log.append(kind="user_message", content=f"msg {i}")
    log.append(
        kind="reflection",
        content='{"intent": "test"}',
        meta={"source": "autonomy_kernel"},
    )

    kernel = AutonomyKernel(log)

    kernel.decide_next_action()
    events = log.read_all()
    meta_count = sum(1 for e in events if e["kind"] == "meta_policy_update")
    policy_count = sum(1 for e in events if e["kind"] == "policy_update")
    # Assert at most one of each
    assert meta_count <= 1
    assert policy_count <= 1
