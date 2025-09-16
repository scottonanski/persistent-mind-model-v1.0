from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.tracker import CommitmentTracker
from pmm.commitments.detectors import RegexCommitmentDetector


def _open_commitment(ct: CommitmentTracker, text: str) -> str:
    # Ensure phrasing that the RegexCommitmentDetector recognizes
    phrase = text if text.lower().startswith("i will") else f"I will {text}"
    added = ct.process_assistant_reply(phrase)
    assert added and len(added) == 1
    return added[0]


def test_logs_evidence_before_close(tmp_path, monkeypatch):
    db = tmp_path / "evidence1.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    _ = _open_commitment(ct, "write the report today.")

    closed = ct.process_evidence("Done: I wrote the report and pushed it.")
    assert closed == []

    events = log.read_all()
    kinds = [e.get("kind") for e in events]
    # Ensure evidence_candidate occurs before commitment_close
    assert "evidence_candidate" in kinds
    # Find indices
    _ = next(i for i, e in enumerate(events) if e.get("kind") == "evidence_candidate")
    # No close without artifact
    assert "commitment_close" not in kinds


def test_no_close_without_evidence(tmp_path, monkeypatch):
    db = tmp_path / "evidence2.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    _ = _open_commitment(ct, "draft a design doc.")

    closed = ct.process_evidence("Chit-chat with no progress.")
    assert closed == []

    kinds = [e.get("kind") for e in log.read_all()]
    assert "commitment_close" not in kinds
    # also no candidate
    assert "evidence_candidate" not in kinds


def test_idempotent_candidates(tmp_path, monkeypatch):
    db = tmp_path / "evidence3.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    _ = _open_commitment(ct, "update probe docs.")

    # First tick
    _ = ct.process_evidence("Done: updated the docs")
    # Second adjacent tick with same snippet
    _ = ct.process_evidence("Done: updated the docs")

    kinds = [e.get("kind") for e in log.read_all()]
    # Only one evidence_candidate despite two adjacent detections
    assert kinds.count("evidence_candidate") == 1


def test_deterministic_scoring_and_threshold(tmp_path):
    db = tmp_path / "evidence4.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    # Open commitment and build synthetic recent events
    cid = _open_commitment(ct, "write the report")
    events = log.read_all() + [
        {
            "kind": "response",
            "content": "Done: I wrote the report and pushed it.",
            "meta": {},
        },
    ]
    open_map = build_self_model(log.read_all()).get("commitments", {}).get("open", {})
    open_list = [{"cid": k, "text": v.get("text")} for k, v in open_map.items()]

    cands = ct.find_evidence(events, open_list, recent_window=10)
    assert cands, "expected a candidate above threshold"
    top = sorted(cands, key=lambda t: (-float(t[1]), str(t[0])))[0]
    assert top[0] == cid
    assert top[1] >= 0.70

    # Pure keyword-only below threshold: unrelated content
    events2 = log.read_all() + [
        {"kind": "response", "content": "brainstorm ideas; plan tomorrow", "meta": {}},
    ]
    cands2 = ct.find_evidence(events2, open_list, recent_window=10)
    # Filter by threshold: ensure none meet >=0.7 (caller enforces threshold)
    assert all(score < 0.70 for _, score, _ in cands2)
