from __future__ import annotations

import json

from pmm_v2.adapters.dummy_adapter import DummyAdapter
from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.autonomy_kernel import AutonomyKernel
from pmm_v2.runtime.loop import RuntimeLoop


def test_decision_is_deterministic_without_ledger_changes():
    log = EventLog(":memory:")
    kernel = AutonomyKernel(log)

    first = kernel.decide_next_action()
    second = kernel.decide_next_action()

    assert first == second
    assert first.decision == "idle"


def test_run_tick_appends_autonomy_tick_and_reflection():
    log = EventLog(":memory:")
    log.append(kind="user_message", content="u1", meta={})
    log.append(kind="assistant_message", content="a1", meta={})
    log.append(kind="metrics_turn", content="provider:dummy", meta={})

    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), replay=True)
    decision = loop.run_tick(slot=0, slot_id="test_slot_0")

    assert decision.decision == "reflect"
    kinds = [event["kind"] for event in log.read_all()]
    assert "autonomy_tick" in kinds
    assert kinds[-1] == "reflection"


def test_run_tick_idle_still_logs_event():
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), replay=True)
    decision = loop.run_tick(slot=0, slot_id="test_slot_0")
    assert decision.decision == "idle"
    kinds = [event["kind"] for event in log.read_all()]
    assert kinds[-1] == "autonomy_tick"


def test_summary_decision_fires_when_interval_met():
    log = EventLog(":memory:")
    log.append(kind="summary_update", content="{}", meta={})
    log.append(kind="user_message", content="u1", meta={})
    log.append(kind="assistant_message", content="a1", meta={})
    log.append(kind="metrics_turn", content="provider:dummy", meta={})
    log.append(kind="reflection", content="r1", meta={"source": "autonomy_kernel"})

    kernel = AutonomyKernel(log, thresholds={"summary_interval": 3})
    decision = kernel.decide_next_action()

    assert decision.decision == "summarize"


def test_rule_table_event_only_appended_once():
    log = EventLog(":memory:")
    RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    first_pass = [
        event for event in log.read_all() if event["kind"] == "autonomy_rule_table"
    ]
    assert len(first_pass) == 1

    RuntimeLoop(eventlog=log, adapter=DummyAdapter())
    second_pass = [
        event for event in log.read_all() if event["kind"] == "autonomy_rule_table"
    ]
    assert len(second_pass) == 1


def _open_monitor_goal(log: EventLog, cid: str = "goal_monitor_rsm") -> None:
    log.append(
        kind="commitment_open",
        content="Commitment opened: monitor_rsm_evolution",
        meta={"cid": cid, "goal": "monitor_rsm_evolution", "source": "autonomy_kernel"},
    )


def _pad_events(log: EventLog, count: int) -> None:
    for idx in range(count):
        log.append(
            kind="test_event",
            content=f"pad-{idx}",
            meta={},
        )


def _record_gap_events(log: EventLog, topic: str, count: int = 4) -> None:
    for idx in range(count):
        log.append(
            kind="assistant_message",
            content=f"Claim: failed analysis {topic} {idx}",
            meta={"topic": topic},
        )


def test_autonomy_triggers_rsm_diff_on_monitor_goal():
    log = EventLog(":memory:")
    log.append(kind="summary_update", content="{}", meta={})
    _open_monitor_goal(log)
    for idx in range(6):
        log.append(
            kind="assistant_message",
            content=f"Determinism ensures consistent outcome {idx}",
            meta={},
        )
    _pad_events(log, 45)

    kernel = AutonomyKernel(log)
    before = len(
        [
            e
            for e in log.read_all()
            if e["kind"] == "reflection"
            and e.get("meta", {}).get("goal") == "monitor_rsm_evolution"
        ]
    )
    kernel.decide_next_action()
    after = len(
        [
            e
            for e in log.read_all()
            if e["kind"] == "reflection"
            and e.get("meta", {}).get("goal") == "monitor_rsm_evolution"
        ]
    )
    assert after == before + 1


def test_rsm_diff_reflection_includes_delta():
    log = EventLog(":memory:")
    log.append(kind="summary_update", content="{}", meta={})
    _open_monitor_goal(log, cid="monitor_rsm_delta")
    for idx in range(7):
        log.append(
            kind="assistant_message",
            content=f"Determinism strategy update {idx}",
            meta={},
        )
    _pad_events(log, 50)

    kernel = AutonomyKernel(log)
    kernel.decide_next_action()

    reflections = [
        e
        for e in log.read_all()
        if e["kind"] == "reflection"
        and e.get("meta", {}).get("goal") == "monitor_rsm_evolution"
    ]
    assert reflections, "expected monitor reflection"
    last_reflection = reflections[-1]
    payload = json.loads(last_reflection["content"])
    assert payload["tendencies_delta"]["determinism_emphasis"] >= 6
    assert payload["from_event"] < payload["to_event"]


def test_monitor_goal_closes_on_stable_rsm():
    log = EventLog(":memory:")
    log.append(kind="summary_update", content="{}", meta={})
    _open_monitor_goal(log, cid="monitor_rsm_stable")
    _pad_events(log, 60)

    kernel = AutonomyKernel(log)
    kernel.decide_next_action()

    events = log.read_all()
    closing_events = [
        e
        for e in events
        if e["kind"] == "commitment_close"
        and e.get("meta", {}).get("goal") == "monitor_rsm_evolution"
    ]
    assert closing_events, "monitor goal should close when RSM stable"
    reflections = [
        e
        for e in events
        if e["kind"] == "reflection"
        and e.get("meta", {}).get("goal") == "monitor_rsm_evolution"
    ]
    assert not reflections, "no reflection expected when RSM stable"


def _gap_heavy_log() -> EventLog:
    log = EventLog(":memory:")
    log.append(kind="user_message", content="need insights", meta={})
    for topic in ("alpha", "beta", "gamma", "delta"):
        _record_gap_events(log, topic, count=1)
    log.append(kind="metrics_turn", content="provider:dummy", meta={})
    return log


def test_autonomy_opens_internal_goal_when_gaps_gt_3():
    log = _gap_heavy_log()
    kernel = AutonomyKernel(log)

    kernel.decide_next_action()

    gap_commitments = [
        e
        for e in log.read_all()
        if e["kind"] == "commitment_open"
        and e.get("meta", {}).get("goal") == AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS
    ]
    assert len(gap_commitments) == 1
    meta = gap_commitments[0]["meta"]
    assert meta["origin"] == "autonomy_kernel"
    assert meta["reason"] == "4 unresolved singleton intents"


def test_gap_goal_included_in_reflection_payload():
    log = EventLog(":memory:")
    kernel = AutonomyKernel(log)
    cid = kernel.commitment_manager.open_internal(
        AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS, reason="gaps=5"
    )
    log.append(kind="metrics_turn", content="provider:dummy", meta={})

    kernel.reflect(
        eventlog=log,
        meta_extra={"source": "autonomy_kernel"},
        staleness_threshold=10,
        auto_close_threshold=20,
    )

    reflections = [e for e in log.read_all() if e["kind"] == "reflection"]
    assert reflections, "reflection expected"
    payload = json.loads(reflections[-1]["content"])
    assert cid in payload["internal_goals"]


def test_execute_analyze_gaps_creates_reflection():
    log = _gap_heavy_log()
    kernel = AutonomyKernel(log)

    # Open the gap goal
    kernel.commitment_manager.open_internal(
        AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS, reason="test"
    )

    initial_reflections = [e for e in log.read_all() if e["kind"] == "reflection"]

    kernel.execute_internal_goal(AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS)

    final_reflections = [e for e in log.read_all() if e["kind"] == "reflection"]
    assert len(final_reflections) == len(initial_reflections) + 1
    new_reflection = final_reflections[-1]
    payload = json.loads(new_reflection["content"])
    assert payload["intent"] == "gap_analysis"
    assert "Unresolved:" in payload["outcome"]
    assert new_reflection["meta"]["goal"] == AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS


def test_execute_closes_internal_goal_after_analysis():
    log = _gap_heavy_log()
    kernel = AutonomyKernel(log)

    # Open the gap goal
    cid = kernel.commitment_manager.open_internal(
        AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS, reason="test"
    )

    kernel.execute_internal_goal(AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS)

    close_events = [
        e
        for e in log.read_all()
        if e["kind"] == "commitment_close" and e.get("meta", {}).get("cid") == cid
    ]
    assert len(close_events) == 1
    assert close_events[0]["meta"]["outcome"] == "analyzed"


def test_no_duplicate_gap_goal():
    log = _gap_heavy_log()
    kernel = AutonomyKernel(log)

    # Manually open the goal
    cid = kernel.commitment_manager.open_internal(
        AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS, reason="test"
    )

    kernel.decide_next_action()
    open_events = [
        e
        for e in log.read_all()
        if e["kind"] == "commitment_open"
        and e.get("meta", {}).get("goal") == AutonomyKernel.INTERNAL_GOAL_ANALYZE_GAPS
    ]
    assert len(open_events) == 1
    assert open_events[0]["meta"]["cid"] == cid


def test_internal_goal_opens_at_gap_4():
    log = EventLog(":memory:")
    kernel = AutonomyKernel(log)

    # Create 4 unresolved intents (count == 1)
    for topic in ("topic1", "topic2", "topic3", "topic4"):
        log.append(
            kind="assistant_message",
            content=f"CLAIM: failed on {topic}",
            meta={"topic": topic},
        )

    # Add a metrics turn to allow reflection
    log.append(kind="metrics_turn", content="provider:dummy", meta={})

    kernel.decide_next_action()

    gap_commitments = [
        e
        for e in log.read_all()
        if e["kind"] == "commitment_open"
        and e.get("meta", {}).get("goal") == "analyze_knowledge_gaps"
    ]
    assert len(gap_commitments) == 1
    meta = gap_commitments[0]["meta"]
    assert meta["origin"] == "autonomy_kernel"
    assert "unresolved singleton intents" in meta["reason"]
