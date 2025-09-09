from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.tracker import CommitmentTracker
from pmm.commitments.detectors import RegexCommitmentDetector


def test_text_only_evidence_default_allows_closure(tmp_path, monkeypatch):
    # Default: PMM_REQUIRE_ARTIFACT_EVIDENCE not set => allow text-only
    monkeypatch.delenv("PMM_REQUIRE_ARTIFACT_EVIDENCE", raising=False)

    db = tmp_path / "e2e.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    opened = ct.process_assistant_reply("I will write probe docs today.")
    assert opened and len(opened) == 1
    cid = opened[0]

    closed = ct.process_evidence("Done: wrote the docs")
    assert closed == [cid]

    model = build_self_model(log.read_all())
    assert cid not in model.get("commitments", {}).get("open", {})


def test_text_only_strict_requires_artifact(tmp_path, monkeypatch):
    # Strict: PMM_REQUIRE_ARTIFACT_EVIDENCE=1 => text-only should not close
    monkeypatch.setenv("PMM_REQUIRE_ARTIFACT_EVIDENCE", "1")

    db = tmp_path / "e2e_strict.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    opened = ct.process_assistant_reply("I will write probe docs today.")
    assert opened and len(opened) == 1
    cid = opened[0]

    closed = ct.process_evidence("Done: wrote the docs")
    assert closed == []

    model = build_self_model(log.read_all())
    # Still open due to lack of artifact in strict mode
    assert cid in model.get("commitments", {}).get("open", {})
