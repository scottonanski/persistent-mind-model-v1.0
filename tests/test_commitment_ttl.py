import datetime as _dt

from pmm.commitments.tracker import CommitmentTracker
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model


def test_ttl_expiration_generates_event_and_closes(tmp_path, monkeypatch):
    # Compute a future 'now' beyond default TTL relative to open timestamp
    db = tmp_path / "ttl.db"
    log = EventLog(str(db))
    tracker = CommitmentTracker(eventlog=log)
    text = "I will complete the project by tomorrow."
    cid = tracker.add_commitment(text, source="test1")
    assert cid

    # Compute a future 'now' beyond the default TTL (24h) relative to the open event timestamp
    evs = log.read_all()
    open_ts = next(e["ts"] for e in evs if e["kind"] == "commitment_open")
    now_dt = _dt.datetime.fromisoformat(open_ts.replace("Z", "+00:00")) + _dt.timedelta(
        hours=25
    )
    now_iso = now_dt.isoformat()

    expired = tracker.expire_old_commitments(now_iso=now_iso)
    assert cid in expired

    kinds = [e["kind"] for e in log.read_all()]
    assert "commitment_expire" in kinds
    model = build_self_model(log.read_all())
    assert cid not in model.get("commitments", {}).get("open", {})


def test_dedup_prevents_spam_within_window(tmp_path):
    db = tmp_path / "dedup.db"
    log = EventLog(str(db))
    tracker = CommitmentTracker(eventlog=log)
    text = "I will complete the project by tomorrow."
    cid1 = tracker.add_commitment(text, source="test2")
    assert cid1

    # Attempt to add a similar commitment shortly after
    cid2 = tracker.add_commitment(text, source="test3")
    assert cid2 == ""  # Duplicate should be ignored
    kinds = [e["kind"] for e in log.read_all()]
    assert kinds.count("commitment_open") == 1
