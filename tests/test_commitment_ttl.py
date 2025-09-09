import datetime as dt

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.tracker import CommitmentTracker
from pmm.commitments.detectors import RegexCommitmentDetector


def test_ttl_expiration_generates_event_and_closes(tmp_path, monkeypatch):
    # TTL 1 hour for test simplicity
    monkeypatch.setenv("PMM_COMMITMENT_TTL_HOURS", "1")

    db = tmp_path / "ttl.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    # Open a commitment now
    opened = ct.process_assistant_reply("I will write docs.")
    assert opened and len(opened) == 1
    cid = opened[0]

    # Move time forward 2 hours to force TTL
    future = (dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)).isoformat()
    expired = ct.expire_old_commitments(now_iso=future)
    assert cid in expired

    events = log.read_all()
    kinds = [e["kind"] for e in events]
    assert "commitment_expire" in kinds
    # Projection treats it as closed
    model = build_self_model(events)
    assert cid not in model.get("commitments", {}).get("open", {})


def test_dedup_prevents_spam_within_window(tmp_path, monkeypatch):
    monkeypatch.setenv("PMM_COMMITMENT_DEDUP_WINDOW", "5")

    db = tmp_path / "dedup.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    opened1 = ct.process_assistant_reply("I will write docs.")
    assert opened1 and len(opened1) == 1

    opened2 = ct.process_assistant_reply("I will write docs.")
    # Dedup means no new cid opened on the second identical plan
    assert opened2 == []

    events = log.read_all()
    # Only one commitment_open should exist
    assert sum(1 for e in events if e["kind"] == "commitment_open") == 1
