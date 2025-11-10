# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""test_autonomy_tracker.py — deterministic rebuild + emit cadence."""

from __future__ import annotations

import json
import pytest

from pmm.core.event_log import EventLog
from pmm.core.autonomy_tracker import AutonomyTracker


@pytest.fixture
def log() -> EventLog:
    return EventLog(":memory:")


def _tick(log: EventLog, decision: str) -> None:
    payload = json.dumps(
        {"decision": decision, "reasoning": "test", "evidence": [1]},
        sort_keys=True,
        separators=(",", ":"),
    )
    log.append(
        kind="autonomy_tick", content=payload, meta={"source": "autonomy_kernel"}
    )


def _reflect(log: EventLog, id: int) -> None:
    content = '{"intent":"test","outcome":"done","next":"continue"}'
    log.append(
        kind="reflection", content=content, meta={"source": "autonomy_kernel", "id": id}
    )


def test_rebuild_equals_incremental(log: EventLog) -> None:
    t1 = AutonomyTracker(log)
    t2 = AutonomyTracker(log)

    _tick(log, "reflect")
    _reflect(log, 2)
    _tick(log, "idle")
    _tick(log, "summarize")

    t2.rebuild()
    assert t1.get_metrics() == t2.get_metrics()


def test_emits_every_10_ticks(log: EventLog) -> None:
    tracker = AutonomyTracker(log)  # noqa: F841

    for i in range(20):
        _tick(log, "reflect" if i % 3 == 0 else "idle")
        if i % 5 == 0:
            _reflect(log, i + 100)

    metrics_evts = [e for e in log.read_all() if e["kind"] == "autonomy_metrics"]
    assert len(metrics_evts) == 2
    last = json.loads(metrics_evts[-1]["content"])
    assert last["ticks_total"] == 20
    assert last["reflect_count"] == 7  # 0,3,6,9,12,15,18
    assert last["last_reflection_id"] == 21  # last reflection event id


def test_idempotent_no_emit_when_replay(log: EventLog) -> None:
    tracker = AutonomyTracker(log)
    for _ in range(10):
        _tick(log, "idle")
    assert any(e["kind"] == "autonomy_metrics" for e in log.read_all())

    before_len = len(log.read_all())
    for ev in log.read_all():
        if ev["kind"] == "autonomy_tick":
            tracker.sync(ev)
    assert len(log.read_all()) == before_len


def test_open_commitments_matches_ledger(log: EventLog) -> None:
    tracker = AutonomyTracker(log)
    log.append(kind="commitment_open", content="test commitment 1", meta={})
    log.append(kind="commitment_open", content="test commitment 2", meta={})
    log.append(kind="commitment_close", content="test close 1", meta={})
    _tick(log, "idle")
    assert tracker.get_metrics()["open_commitments"] == 1
    log.append(kind="commitment_close", content="test close 2", meta={})
    _tick(log, "idle")
    assert tracker.get_metrics()["open_commitments"] == 0


def test_last_reflection_id_from_autonomy_kernel_only(log: EventLog) -> None:
    tracker = AutonomyTracker(log)
    log.append(
        kind="reflection", content="user reflection", meta={"source": "user_turn"}
    )
    log.append(
        kind="reflection",
        content="kernel reflection",
        meta={"source": "autonomy_kernel", "id": 100},
    )
    _tick(log, "idle")
    assert tracker.get_metrics()["last_reflection_id"] == 2


def test_cli_rebuild_shows_correct_telemetry(log: EventLog) -> None:
    # Simulate runtime: append events
    for i in range(5):
        _tick(log, "reflect" if i % 2 == 0 else "idle")
    _reflect(log, 100)

    # Simulate CLI /metrics load
    tracker = AutonomyTracker(log)
    tracker.rebuild()

    m = tracker.get_metrics()
    assert m["ticks_total"] == 5
    assert m["reflect_count"] == 3
    assert m["last_reflection_id"] == 6


def test_last_reflection_id_is_set():
    log = EventLog(":memory:")
    log.append(kind="reflection", content="{}", meta={"source": "autonomy_kernel"})
    tracker = AutonomyTracker(log)
    tracker.rebuild()
    assert tracker.get_metrics()["last_reflection_id"] == 1
