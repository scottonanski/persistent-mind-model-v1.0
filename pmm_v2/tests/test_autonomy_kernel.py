from __future__ import annotations

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
