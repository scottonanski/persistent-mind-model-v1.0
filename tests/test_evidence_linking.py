from pmm.commitments.tracker import CommitmentTracker
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model


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
    result = ct.close_reflection_on_next("wrote the docs")
    assert result is None  # New method returns None, not True

    model = build_self_model(log.read_all())
    # Commitment should be closed (not in open map)
    assert cid not in model.get("commitments", {}).get("open", {})
