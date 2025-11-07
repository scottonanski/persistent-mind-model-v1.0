from __future__ import annotations

import json
from pathlib import Path

from pmm.core.autonomy_tracker import AutonomyTracker
from pmm.core.event_log import EventLog
from pmm.core.ledger_metrics import compute_metrics


def _mkdb(tmp_path: Path) -> str:
    return str(tmp_path / "ledger_metrics.db")


def test_compute_metrics_kernel_knowledge_gaps(tmp_path):
    db = _mkdb(tmp_path)
    log = EventLog(db)
    log.append(
        kind="assistant_message",
        content="claim: failed to retrieve supporting evidence",
        meta={"topic": "epistemics"},
    )

    metrics = compute_metrics(db)

    assert metrics["event_count"] == 1
    assert metrics["kernel_knowledge_gaps"] == 1
    assert metrics["open_commitments"] == 0


def test_compute_metrics_includes_autonomy_tracker_metrics(tmp_path):
    db = _mkdb(tmp_path)
    log = EventLog(db)
    tracker = AutonomyTracker(log)

    log.append(
        kind="autonomy_tick",
        content=json.dumps({"decision": "reflect"}),
        meta={},
    )
    log.append(
        kind="autonomy_tick",
        content=json.dumps({"decision": "summarize"}),
        meta={},
    )
    log.append(
        kind="autonomy_tick",
        content=json.dumps({"decision": "idle"}),
        meta={},
    )
    reflection_id = log.append(
        kind="reflection",
        content=json.dumps({"intent": "observe"}),
        meta={"source": "autonomy_kernel"},
    )
    log.append(
        kind="commitment_open",
        content="commitment:c1",
        meta={"cid": "c1"},
    )

    metrics = compute_metrics(db, tracker)

    assert metrics["event_count"] == 5
    assert metrics["open_commitments"] == 1

    autonomy_metrics = metrics["autonomy_metrics"]
    assert autonomy_metrics["ticks_total"] == 3
    assert autonomy_metrics["reflect_count"] == 1
    # Ledger-only: no summary_update events were written in this test,
    # so summarize_count must be 0. Intention count captures the tick.
    assert autonomy_metrics["summarize_count"] == 0
    assert autonomy_metrics["intention_summarize_count"] == 1
    assert autonomy_metrics["idle_count"] == 1
    assert autonomy_metrics["last_reflection_id"] == reflection_id
    assert autonomy_metrics["open_commitments"] == 1


def test_replay_speed_metric_under_threshold(tmp_path):
    db = _mkdb(tmp_path)
    log = EventLog(db)
    # Create 500 events with unique content for stable hashing
    for i in range(500):
        log.append(kind="test_event", content=f"e{i}", meta={})

    metrics = compute_metrics(db)
    speed = metrics.get("replay_speed_ms")
    assert isinstance(speed, float)
    # Verify O(n) perf stays below ~0.01 ms/event with small tolerance
    assert speed < 0.015
