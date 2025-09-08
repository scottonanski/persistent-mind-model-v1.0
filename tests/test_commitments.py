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


# --- New detector DI and evidence tests ---
import pytest
from pmm.commitments.detectors import RegexCommitmentDetector, SemanticCommitmentDetector


@pytest.mark.parametrize("detector_cls", [RegexCommitmentDetector, SemanticCommitmentDetector])
def test_detector_interface_finds_plans(tmp_path, detector_cls, monkeypatch):
    # Ensure semantic path is selectable but stub defers to regex until embeddings are wired
    if detector_cls is SemanticCommitmentDetector:
        monkeypatch.setenv("PMM_DETECTOR", "semantic")

    db = tmp_path / "det.db"
    log = EventLog(str(db))
    t = CommitmentTracker(log, detector=detector_cls())

    added = t.process_assistant_reply("Okay, I will prepare the summary and send it later today.")
    assert isinstance(added, list)
    assert len(added) >= 1


def test_done_evidence_closes_most_recent_when_ambiguous(tmp_path, monkeypatch):
    # Allow text-only evidence for tests
    monkeypatch.setenv("TEST_ALLOW_TEXT_ONLY_EVIDENCE", "1")

    db = tmp_path / "ev_done.db"
    log = EventLog(str(db))
    t = CommitmentTracker(log, detector=RegexCommitmentDetector())

    h1 = t.add_commitment("I will prepare the summary.")
    h2 = t.add_commitment("I will write probe docs.")

    closed = t.process_evidence("Done: wrote the docs")
    assert isinstance(closed, list)
    assert closed and closed[0] == h2  # most recent open when ambiguous favors latest


def test_done_evidence_closes_by_detail_substring(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_ALLOW_TEXT_ONLY_EVIDENCE", "1")

    db = tmp_path / "ev_done2.db"
    log = EventLog(str(db))
    t = CommitmentTracker(log, detector=RegexCommitmentDetector())

    h1 = t.add_commitment("I will prepare the summary.")
    h2 = t.add_commitment("I will write probe docs.")

    closed = t.process_evidence("Completed: summary")
    assert isinstance(closed, list)
    assert closed and closed[0] == h1

