from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.tracker import CommitmentTracker
from pmm.commitments.detectors import RegexCommitmentDetector


def test_text_only_evidence_closes_without_artifact(tmp_path, monkeypatch):
    db = tmp_path / "e2e.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    opened = ct.process_assistant_reply("I will write probe docs today.")
    assert opened and len(opened) == 1
    cid = opened[0]

    closed = ct.process_evidence("Done: wrote the docs")
    assert closed == [cid]

    model = build_self_model(log.read_all())
    # Closed via text evidence
    assert cid not in model.get("commitments", {}).get("open", {})


def test_close_requires_artifact_metadata(tmp_path, monkeypatch):
    db = tmp_path / "e2e_strict.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    opened = ct.process_assistant_reply("I will write probe docs today.")
    assert opened and len(opened) == 1
    cid = opened[0]

    # Provide an artifact to close
    closed = ct.close_with_evidence(
        cid, "done", "docs completed", artifact="/path/doc.pdf"
    )
    assert closed is True
