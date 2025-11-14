# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_autonomy_end_to_end.py
"""End-to-end determinism and replay tests for full autonomy system."""

import json
from collections import Counter

from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel


def test_end_to_end_replay_determinism():
    """Test that autonomy runs are deterministic under replay."""
    # Seed initial events
    log = EventLog(":memory:")
    for i in range(50):
        log.append(kind="user_message", content=f"user {i}")
        log.append(kind="assistant_message", content=f"response {i}\nCOMMIT: task{i}")
        if i % 5 == 0:
            log.append(
                kind="reflection",
                content='{"intent": "reflect"}',
                meta={"source": "autonomy_kernel"},
            )
            log.append(kind="policy_update", content="adjust")
        if i % 10 == 0:
            log.append(
                kind="claim",
                content='CLAIM:memory={"domain": "memory", "value": "short"}',
            )
            log.append(
                kind="outcome_observation",
                content=json.dumps(
                    {
                        "commitment_id": f"c{i}",
                        "action_kind": "reflect",
                        "action_payload": "test",
                        "observed_result": "success",
                        "evidence_event_ids": [i],
                    }
                ),
            )

    # Run 1
    kernel1 = AutonomyKernel(log)
    for _ in range(5):
        kernel1.decide_next_action()

    events_run1 = log.read_all()

    # Replay: reconstruct from run1 events
    log_replay = EventLog(":memory:")
    for e in events_run1:
        log_replay.append(
            kind=e["kind"],
            content=e.get("content"),
            meta=e.get("meta", {}),
        )

    # Run 2 on replay
    kernel2 = AutonomyKernel(log_replay)
    for _ in range(5):
        kernel2.decide_next_action()

    events_run2 = log_replay.read_all()

    # Assert determinism
    assert len(events_run1) <= len(events_run2)  # At most, new events
    # Count event kinds
    kinds1 = Counter(e["kind"] for e in events_run1)
    kinds2 = Counter(e["kind"] for e in events_run2)
    # Core events should match
    assert kinds1["user_message"] == kinds2["user_message"]
    assert kinds1["assistant_message"] == kinds2["assistant_message"]
    # Idempotent events should not duplicate excessively
    assert kinds2["stability_metrics"] <= kinds1["stability_metrics"] + 1
    assert kinds2["coherence_check"] <= kinds1["coherence_check"] + 1


def test_bounded_behavior():
    """Test that autonomy scales with bounded new events."""
    log = EventLog(":memory:")
    # 1000 simple events
    for i in range(1000):
        log.append(kind="user_message", content=f"user {i}")
        log.append(kind="assistant_message", content=f"response {i}")

    kernel = AutonomyKernel(log)
    initial_count = len(log.read_all())

    for _ in range(5):
        kernel.decide_next_action()

    after_count = len(log.read_all())
    new_events = after_count - initial_count

    # Assert bounded: at most a few new events per decision
    assert new_events <= 20  # Conservative bound
    events = log.read_all()
    kinds = Counter(e["kind"] for e in events)
    # No explosion of any kind
    assert kinds["autonomy_rule_table"] <= 1
