from pmm.storage.eventlog import EventLog
from pmm.commitments.tracker import CommitmentTracker
from pmm.commitments.detectors import RegexCommitmentDetector
from pmm.runtime.loop import emit_reflection
from pmm.runtime.introspection import run_audit


def _open_commitment(ct: CommitmentTracker, text: str) -> str:
    phrase = text if text.lower().startswith("i will") else f"I will {text}"
    added = ct.process_assistant_reply(phrase)
    assert added and len(added) == 1
    return added[0]


def test_audit_flags_close_without_candidate(tmp_path, monkeypatch):
    db = tmp_path / "audit1.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    cid = _open_commitment(ct, "write the report")

    # Allow text-only closes in tests
    monkeypatch.setenv("TEST_ALLOW_TEXT_ONLY_EVIDENCE", "1")
    # Force a close directly without emitting evidence_candidate
    ct.close_with_evidence(cid, evidence_type="done", description="finished")

    audits = run_audit(log.read_all(), window=50)
    cats = [a.get("meta", {}).get("category") for a in audits]
    assert "closure-audit" in cats


def test_audit_detects_duplicate_close(tmp_path, monkeypatch):
    db = tmp_path / "audit2.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    cid = _open_commitment(ct, "write the report")

    monkeypatch.setenv("TEST_ALLOW_TEXT_ONLY_EVIDENCE", "1")
    assert ct.close_with_evidence(cid, evidence_type="done", description="done") is True
    # Manually append a second close to simulate bad duplicate close (no re-open)
    log.append(
        kind="commitment_close",
        content="",
        meta={"cid": cid, "evidence_type": "done", "description": "duplicate"},
    )

    audits = run_audit(log.read_all(), window=50)
    cats = [a.get("meta", {}).get("category") for a in audits]
    assert "duplicate-close" in cats


def test_audit_orphan_evidence(tmp_path, monkeypatch):
    db = tmp_path / "audit3.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    _ = _open_commitment(ct, "update docs")

    monkeypatch.setenv("TEST_ALLOW_TEXT_ONLY_EVIDENCE", "1")
    # Emit an orphan candidate by appending it directly without a close
    # Find the open cid from projection
    events_now = log.read_all()
    # Extract open cid from last commitment_open
    open_cid = None
    for ev in reversed(events_now):
        if ev.get("kind") == "commitment_open":
            open_cid = (ev.get("meta") or {}).get("cid")
            break
    assert open_cid
    log.append(
        kind="evidence_candidate",
        content="",
        meta={"cid": open_cid, "score": 0.9, "snippet": "updated docs"},
    )

    audits = run_audit(log.read_all(), window=50)
    cats = [a.get("meta", {}).get("category") for a in audits]
    assert "orphan-evidence" in cats


def test_audit_reflection_fact_check(tmp_path):
    db = tmp_path / "audit4.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    _ = _open_commitment(ct, "finish the report")

    # Emit a reflection claiming done, but no close
    emit_reflection(log, content="I finished the report today.")

    audits = run_audit(log.read_all(), window=50)
    # There should be a fact-check audit
    cats = [a.get("meta", {}).get("category") for a in audits]
    assert "fact-check" in cats
