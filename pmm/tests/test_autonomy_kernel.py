# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel


def _append_tick(log: EventLog, decision: str = "idle") -> int:
    payload = json.dumps(
        {"decision": decision, "reasoning": "t", "evidence": []}, sort_keys=True
    )
    return log.append(
        kind="autonomy_tick",
        content=payload,
        meta={"source": "autonomy_kernel", "slot": 0, "slot_id": "t"},
    )


def _append_metrics_turn(log: EventLog) -> int:
    return log.append(
        kind="metrics_turn",
        content="provider:dummy,model:x,in_tokens:1,out_tokens:1,lat_ms:1",
        meta={},
    )


def test_decide_reflect_when_no_autonomy_reflection_yet():
    log = EventLog(":memory:")
    _append_metrics_turn(log)
    # One tick so kernel has something to read
    _append_tick(log, decision="idle")
    kernel = AutonomyKernel(log)
    decision = kernel.decide_next_action()
    assert decision.decision == "reflect"


def test_reflection_idempotent_skip_on_identical_content():
    log = EventLog(":memory:")
    _append_metrics_turn(log)
    # Add minimal structure so reflect() can compute state deterministically
    _append_tick(log, decision="idle")
    kernel = AutonomyKernel(log)
    # First reflect should append
    rid1 = kernel.reflect(
        log,
        {"source": "autonomy_kernel"},
        staleness_threshold=20,
        auto_close_threshold=27,
    )
    assert isinstance(rid1, int)
    # Second reflect over identical ledger slice should skip (None)
    rid2 = kernel.reflect(
        log,
        {"source": "autonomy_kernel"},
        staleness_threshold=20,
        auto_close_threshold=27,
    )
    assert rid2 is None


def test_metrics_emit_every_10_ticks():
    log = EventLog(":memory:")
    _append_metrics_turn(log)
    kernel = AutonomyKernel(log)
    # 9 ticks: no metrics yet
    for _ in range(9):
        _append_tick(log, decision="idle")
        kernel._maybe_emit_autonomy_metrics()
    assert not any(e.get("kind") == "autonomy_metrics" for e in log.read_all())
    # 10th tick triggers emit
    _append_tick(log, decision="idle")
    kernel._maybe_emit_autonomy_metrics()
    mets = [e for e in log.read_all() if e.get("kind") == "autonomy_metrics"]
    assert len(mets) == 1
    data = json.loads(mets[-1].get("content") or "{}")
    assert data.get("ticks_total") == 10


def test_rsm_significant_change_triggers_reflection():
    log = EventLog(":memory:")
    # Seed metrics
    _append_metrics_turn(log)
    kernel = AutonomyKernel(log)
    # Open internal goal to monitor RSM
    kernel.commitment_manager.open_internal(
        goal=kernel.INTERNAL_GOAL_MONITOR_RSM, reason="test"
    )
    # Append > RSM_EVENT_INTERVAL filler and assistant messages containing the marker
    # RSM_EVENT_INTERVAL is 50 in kernel; create 52 events total after open
    for i in range(40):
        log.append(kind="test_event", content="x", meta={})
    for i in range(12):
        log.append(kind="assistant_message", content="determinism", meta={})

    # Execute goal should append a reflection capturing tendencies_delta
    rid = kernel.execute_internal_goal(kernel.INTERNAL_GOAL_MONITOR_RSM)
    assert isinstance(rid, int)
    ev = log.get(rid)
    assert ev.get("kind") == "reflection"
    meta = ev.get("meta") or {}
    assert meta.get("goal") == kernel.INTERNAL_GOAL_MONITOR_RSM


def test_decision_replay_stability_no_side_effects():
    log = EventLog(":memory:")
    _append_metrics_turn(log)
    kernel = AutonomyKernel(log)
    before = list(log.read_all())
    d1 = kernel.decide_next_action()
    d2 = kernel.decide_next_action()
    after = list(log.read_all())
    # decide_next_action should not mutate the log directly
    assert before == after
    assert d1.decision in {"idle", "reflect", "summarize"}
    assert d2.decision in {"idle", "reflect", "summarize"}


def test_stalled_commitments_trigger_reflect_decision():
    log = EventLog(":memory:")
    # Seed metrics so decide_next_action can proceed past initial idle.
    _append_metrics_turn(log)
    # Configure a large reflection_interval so stalled commitments, not
    # interval length, drive the reflect decision.
    kernel = AutonomyKernel(log, thresholds={"reflection_interval": 1000})

    # Open a general (non-internal) commitment that will become stale.
    cid = kernel.commitment_manager.open_commitment("test stalled commitment")
    assert cid

    # Record an initial autonomy_kernel reflection so the kernel does not
    # immediately reflect just because none exist yet.
    log.append(
        kind="reflection",
        content='{"intent": "initial"}',
        meta={"source": "autonomy_kernel"},
    )

    # Append enough events after the commitment thread to exceed the
    # commitment_staleness threshold.
    staleness = int(kernel.thresholds["commitment_staleness"])
    for i in range(staleness + 1):
        log.append(kind="user_message", content=f"msg {i}", meta={})

    decision = kernel.decide_next_action()
    assert decision.decision == "reflect"
    assert "stalled commitments" in decision.reasoning
    assert decision.evidence
