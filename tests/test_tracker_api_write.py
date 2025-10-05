from pmm.commitments.tracker import api as tracker_api
from pmm.storage.eventlog import EventLog


def _temp_db(tmp_path) -> str:
    return str(tmp_path / "tracker_api_write.db")


def _all_kinds(events: list[dict]) -> list[str]:
    return [str(e.get("kind") or "") for e in events]


def test_add_and_close_commitment(tmp_path):
    db = _temp_db(tmp_path)
    evlog = EventLog(db)

    cid = tracker_api.add_commitment(evlog, text="Ship the product", source="test")
    assert isinstance(cid, str) and cid

    events = evlog.read_all()
    assert any(
        e.get("kind") == "commitment_open" and (e.get("meta") or {}).get("cid") == cid
        for e in events
    )

    # Close with text-only evidence
    ok = tracker_api.close_commitment(
        evlog,
        cid=cid,
        evidence_type="done",
        description="Shipped v1",
        artifact=None,
    )
    assert ok is True

    events2 = evlog.read_all()
    kinds = _all_kinds(events2)
    assert "commitment_close" in kinds

    # Closing again should return False (not open anymore)
    ok2 = tracker_api.close_commitment(
        evlog, cid=cid, evidence_type="done", description="repeat", artifact=None
    )
    assert ok2 is False


def test_expire_and_snooze_idempotency(tmp_path):
    db = _temp_db(tmp_path)
    evlog = EventLog(db)

    cid = tracker_api.add_commitment(evlog, text="Write docs", source="test")
    assert cid

    # Snooze to tick 3
    ok_s1 = tracker_api.snooze_commitment(evlog, cid=cid, until_tick=3)
    assert ok_s1 is True
    # Snoozing to an older/equal tick should be no-op
    assert tracker_api.snooze_commitment(evlog, cid=cid, until_tick=2) is False
    assert tracker_api.snooze_commitment(evlog, cid=cid, until_tick=3) is False
    # Higher tick should succeed
    assert tracker_api.snooze_commitment(evlog, cid=cid, until_tick=5) is True

    # Expire should work once, then be a no-op since no longer open
    ok_e1 = tracker_api.expire_commitment(evlog, cid=cid, reason="manual")
    assert ok_e1 is True
    ok_e2 = tracker_api.expire_commitment(evlog, cid=cid, reason="manual")
    assert ok_e2 is False


def test_rebind_commitment_with_identity_tag(tmp_path):
    db = _temp_db(tmp_path)
    evlog = EventLog(db)

    cid = tracker_api.add_commitment(
        evlog, text="Email Alice about launch", source="test"
    )
    assert cid

    ok = tracker_api.rebind_commitment(
        evlog,
        cid=cid,
        old_name="Alice",
        new_name="Alicia",
        identity_adopt_event_id=123,
        original_text="Email Alice about launch",
    )
    assert ok is True

    events = evlog.read_all()
    found = False
    for e in reversed(events):
        if e.get("kind") != "commitment_rebind":
            continue
        m = e.get("meta") or {}
        if m.get("cid") == cid and m.get("identity_adopt_event_id") == 123:
            found = True
            break
    assert found is True
