from pmm.api.probe import snapshot, snapshot_paged
from pmm.storage.eventlog import EventLog


def test_probe_snapshot_redaction_applies_to_events(tmp_path):
    db_path = tmp_path / "events.db"
    log = EventLog(str(db_path))

    # 1) identity_change
    log.append(kind="identity_change", content="", meta={"name": "Ava"})
    # 2) commitment_open c1
    log.append(
        kind="commitment_open", content="", meta={"cid": "c1", "text": "Ship skeleton"}
    )
    # 3) large reflection
    big_content = "R" * 5000
    big_blob = "X" * 5000
    log.append(kind="reflection", content=big_content, meta={"blob": big_blob})

    # Without redaction
    snap = snapshot(log, limit=10)
    last = snap["events"][-1]
    assert len(last["content"]) > 4000
    assert "blob" in last["meta"]

    # With redaction
    def redact(e: dict) -> dict:
        # trim content to <= 64 chars
        out = dict(e)
        if isinstance(out.get("content"), str) and len(out["content"]) > 64:
            out["content"] = out["content"][:64]
        # remove blob in meta
        meta = dict(out.get("meta") or {})
        meta.pop("blob", None)
        out["meta"] = meta
        return out

    snap_red = snapshot(log, limit=10, redact=redact)
    last_red = snap_red["events"][-1]
    assert len(last_red["content"]) <= 64
    assert "blob" not in last_red["meta"]


def test_probe_snapshot_paged_redaction_and_cursor(tmp_path):
    db_path = tmp_path / "events_paged.db"
    log = EventLog(str(db_path))

    # events: 1) identity_change, 2) open c1, 3) large reflection
    log.append(kind="identity_change", content="", meta={"name": "Ava"})
    log.append(
        kind="commitment_open", content="", meta={"cid": "c1", "text": "Ship skeleton"}
    )
    big_content = "R" * 5000
    big_blob = "X" * 5000
    log.append(kind="reflection", content=big_content, meta={"blob": big_blob})

    def redact(e: dict) -> dict:
        out = dict(e)
        if isinstance(out.get("content"), str) and len(out["content"]) > 64:
            out["content"] = out["content"][:64]
        meta = dict(out.get("meta") or {})
        meta.pop("blob", None)
        out["meta"] = meta
        return out

    # Page 1 (no cursor), limit 2
    page1 = snapshot_paged(log, limit=2, redact=redact)
    ev1 = page1["events"]
    assert len(ev1) == 2
    assert all(len(e.get("content", "")) <= 64 for e in ev1)
    assert all("blob" not in (e.get("meta") or {}) for e in ev1)
    assert page1["next_after_id"] is not None

    # Page 2 (cursor), should return the last event redacted
    page2 = snapshot_paged(log, limit=2, after_id=page1["next_after_id"], redact=redact)
    ev2 = page2["events"]
    assert len(ev2) == 1
    assert all(len(e.get("content", "")) <= 64 for e in ev2)
    assert all("blob" not in (e.get("meta") or {}) for e in ev2)
    assert page2["next_after_id"] is None
