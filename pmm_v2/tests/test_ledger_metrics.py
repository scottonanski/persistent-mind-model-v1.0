from __future__ import annotations

import json
from pathlib import Path

from pmm_v2.core.autonomy_tracker import AutonomyTracker
from pmm_v2.core.event_log import EventLog
from pmm_v2.core.ledger_metrics import compute_metrics


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
    assert autonomy_metrics["summarize_count"] == 1
    assert autonomy_metrics["idle_count"] == 1
    assert autonomy_metrics["last_reflection_id"] == reflection_id
    assert autonomy_metrics["open_commitments"] == 1
