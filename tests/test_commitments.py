import os
from pmm.storage.eventlog import EventLog
from pmm.commitments.tracker import CommitmentTracker


def test_open_then_invalid_close_stays_open(tmp_path):
    db = tmp_path / "ev.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    cid = ct.add_commitment("Ship skeleton")
    ok = ct.close_with_evidence(cid, evidence_type="note", description="not done", artifact=None)
    assert ok is False

    open_map = ct.list_open()
    assert cid in open_map
    assert open_map[cid]["text"] == "Ship skeleton"


def test_open_then_valid_close_removes_from_open(tmp_path):
    db = tmp_path / "ev.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    cid = ct.add_commitment("Write tests")
    ok = ct.close_with_evidence(cid, evidence_type="done", description="tests passing", artifact="report.txt")
    assert ok is True

    open_map = ct.list_open()
    assert cid not in open_map


def test_text_only_evidence_allowed_via_env(tmp_path, monkeypatch):
    db = tmp_path / "ev.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    monkeypatch.setenv("TEST_ALLOW_TEXT_ONLY_EVIDENCE", "1")
    cid = ct.add_commitment("Refactor storage")
    ok = ct.close_with_evidence(cid, evidence_type="done", description="done text-only", artifact=None)
    assert ok is True

    open_map = ct.list_open()
    assert cid not in open_map


def test_reclosing_returns_false(tmp_path):
    db = tmp_path / "ev.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    cid = ct.add_commitment("Finalize design")
    ok1 = ct.close_with_evidence(cid, evidence_type="done", description="complete", artifact="evidence.txt")
    assert ok1 is True

    ok2 = ct.close_with_evidence(cid, evidence_type="done", description="again", artifact="evidence.txt")
    assert ok2 is False

