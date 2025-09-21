from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.tracker import CommitmentTracker


def test_text_only_evidence_closes_without_artifact(tmp_path, monkeypatch):
    db = tmp_path / "e2e.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    cid = ct.add_commitment(
        "write probe docs today", source="test", extra_meta={"reason": "reflection"}
    )
    assert cid

    result = ct.close_reflection_on_next("wrote the docs")
    assert result is None  # New method returns None, not True

    model = build_self_model(log.read_all())
    # Closed via direct commitment close
    assert cid not in model.get("commitments", {}).get("open", {})


def test_close_requires_artifact_metadata(tmp_path, monkeypatch):
    db = tmp_path / "e2e_strict.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    cid = ct.add_commitment("write probe docs today", source="test")
    assert cid

    # Provide an artifact to close
    closed = ct.close_with_evidence(
        cid, "done", "docs completed", artifact="/path/doc.pdf"
    )
    assert closed is True
