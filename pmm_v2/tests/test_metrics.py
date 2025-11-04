from __future__ import annotations

from pathlib import Path

from pmm_v2.core.event_log import EventLog
from pmm_v2.core.ledger_metrics import compute_metrics, append_metrics_if_delta


def _mkdb(tmp_path: Path) -> str:
    return str(tmp_path / "pmm_v2_metrics.db")


def test_compute_metrics_empty(tmp_path):
    db = _mkdb(tmp_path)
    _ = EventLog(db)
    m = compute_metrics(db)
    assert m["event_count"] == 0
    assert m["broken_links"] == 0
    assert m["last_hash"] == "0" * 64
    assert m["kinds"] == {}
    assert m["open_commitments"] == 0
    assert m["closed_commitments"] == 0


def test_compute_metrics_counts_and_chain(tmp_path):
    db = _mkdb(tmp_path)
    log = EventLog(db)

    log.append(kind="config", content="{}", meta={})
    log.append(kind="user_message", content="Hello", meta={})
    log.append(kind="assistant_message", content="Hi", meta={})
    log.append(kind="commitment_open", content="c1", meta={"cid": "c1", "text": "t"})
    log.append(kind="commitment_close", content="c1", meta={"cid": "c1"})

    m = compute_metrics(db)
    assert m["event_count"] == 5
    assert m["kinds"]["config"] == 1
    assert m["kinds"]["user_message"] == 1
    assert m["kinds"]["assistant_message"] == 1
    assert m["kinds"]["commitment_open"] == 1
    assert m["kinds"]["commitment_close"] == 1
    assert m["open_commitments"] == 0
    assert m["closed_commitments"] == 1
    assert m["broken_links"] == 0
    assert isinstance(m["last_hash"], str) and len(m["last_hash"]) == 64


def test_append_metrics_if_delta_idempotent(tmp_path):
    db = _mkdb(tmp_path)
    log = EventLog(db)
    log.append(kind="config", content="{}", meta={})
    log.append(kind="user_message", content="Hello", meta={})

    did1 = append_metrics_if_delta(db)
    assert did1 is True
    did2 = append_metrics_if_delta(db)
    assert did2 is False

    log.append(kind="assistant_message", content="Hi", meta={})
    did3 = append_metrics_if_delta(db)
    assert did3 is True
