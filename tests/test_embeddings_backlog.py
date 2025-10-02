from __future__ import annotations

from pmm.runtime.embeddings_backlog import find_missing_response_eids, process_backlog
from pmm.storage.eventlog import EventLog


def test_find_missing_sorted_and_specific(tmp_path):
    log = EventLog(str(tmp_path / "backlog.db"))
    # Seed two responses and an embedding for the first
    r1 = log.append(kind="response", content="foo", meta={})
    r2 = log.append(kind="response", content="bar", meta={})
    log.append(
        kind="embedding_indexed", content="", meta={"eid": int(r1), "digest": "abcd"}
    )

    missing = find_missing_response_eids(log)
    assert missing == [int(r2)]


def test_process_backlog_indexes_always_on(tmp_path, monkeypatch):
    log = EventLog(str(tmp_path / "backlog2.db"))
    r1 = log.append(kind="response", content="alpha", meta={})
    r2 = log.append(kind="response", content="beta", meta={})
    # Pre-index r1 only
    log.append(
        kind="embedding_indexed",
        content="",
        meta={"eid": int(r1), "digest": "deadbeef"},
    )

    # Embeddings always ON: backlog indexes any missing response deterministically
    summary = process_backlog(log, use_real=True)
    assert summary["processed"] == 1
    assert summary["indexed"] == 1

    # Idempotent: second run should find nothing to index
    summary2 = process_backlog(log, use_real=True)
    assert summary2["processed"] == 0
    assert summary2["indexed"] == 0

    # Verify an embedding_indexed event exists for r2 and points back correctly
    evs = log.read_all()
    emb = next(
        e
        for e in evs
        if e.get("kind") == "embedding_indexed"
        and (e.get("meta") or {}).get("eid") == int(r2)
    )
    assert emb

    # Side-table row should be present if available
    if log.has_embeddings_index:
        cur = log._conn.execute(
            "SELECT COUNT(1) FROM event_embeddings WHERE eid=?", (int(r2),)
        )
        (cnt,) = cur.fetchone()
        assert int(cnt) == 1


def test_process_backlog_indexes_missing_responses(tmp_path, monkeypatch):
    log = EventLog(str(tmp_path / "backlog3.db"))
    _ = log.append(kind="response", content="gamma", meta={})

    # Always indexes
    summary = process_backlog(log)
    assert summary["processed"] == 1
    assert summary["indexed"] == 1
    kinds = [e.get("kind") for e in log.read_all()]
    assert "embedding_indexed" in kinds
    # Idempotent on re-run
    summary2 = process_backlog(log)
    assert summary2["processed"] == 0
    assert summary2["indexed"] == 0
