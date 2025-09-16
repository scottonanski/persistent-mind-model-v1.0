from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.tracker import CommitmentTracker


def test_e2e_done_closes_commitment(tmp_path, monkeypatch):
    db = tmp_path / "e2e.db"
    log = EventLog(str(db))
    ct = CommitmentTracker(log)

    # open explicitly via structural path
    cid = ct.add_commitment(
        "write probe docs today", source="test", extra_meta={"reason": "reflection"}
    )
    assert cid

    # Evidence confirmation via structural helper
    ok = ct.close_reflection_on_next("wrote the docs")
    assert ok is True

    model = build_self_model(log.read_all())
    assert cid not in model.get("commitments", {}).get("open", {})
