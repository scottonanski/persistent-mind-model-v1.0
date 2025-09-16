from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.tracker import CommitmentTracker
from pmm.commitments.detectors import RegexCommitmentDetector


def test_e2e_done_closes_commitment(tmp_path, monkeypatch):
    db = tmp_path / "e2e.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log, detector=RegexCommitmentDetector())

    # open via detector path
    added = ct.process_assistant_reply("Okay, I will write probe docs today.")
    assert added and len(added) == 1
    cid = added[0]

    # Text-only evidence closes when allowed
    closed = ct.process_evidence("Done: wrote the docs")
    assert closed == [cid]

    model = build_self_model(log.read_all())
    assert cid not in model.get("commitments", {}).get("open", {})
