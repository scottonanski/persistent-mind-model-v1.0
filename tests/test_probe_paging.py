from pmm.api.probe import snapshot_paged
from pmm.storage.eventlog import EventLog


def _populate_db(log: EventLog):
    # 1) identity_change
    log.append(kind="identity_change", content="", meta={"name": "Ava"})
    # 2) commitment_open c1
    log.append(
        kind="commitment_open", content="", meta={"cid": "c1", "text": "Ship skeleton"}
    )
    # 3) commitment_open c2
    log.append(
        kind="commitment_open", content="", meta={"cid": "c2", "text": "Write tests"}
    )
    # 4) reflection (arbitrary extra kind)
    log.append(kind="reflection", content="Thinking...", meta={})
    # 5) commitment_close c1
    log.append(kind="commitment_close", content="", meta={"cid": "c1"})


def test_snapshot_paged_by_after_id(tmp_path):
    db_path = tmp_path / "events.db"
    log = EventLog(str(db_path))
    _populate_db(log)

    # Page 1
    page1 = snapshot_paged(log, limit=2)
    ev1 = page1["events"]
    assert len(ev1) == 2
    assert ev1[0]["id"] < ev1[-1]["id"]  # ascending order
    assert page1["next_after_id"] is not None

    # Page 2
    page2 = snapshot_paged(log, limit=2, after_id=page1["next_after_id"])
    ev2 = page2["events"]
    assert len(ev2) == 2
    assert ev2[0]["id"] < ev2[-1]["id"]
    assert page2["next_after_id"] is not None

    # Page 3 (last)
    page3 = snapshot_paged(log, limit=2, after_id=page2["next_after_id"])
    ev3 = page3["events"]
    assert len(ev3) == 1
    assert page3["next_after_id"] is None


def test_snapshot_paged_by_after_ts(tmp_path):
    db_path = tmp_path / "events_ts.db"
    log = EventLog(str(db_path))
    _populate_db(log)

    # Get all events to choose a ts cursor after the first event
    all_events = log.read_all()
    assert len(all_events) == 5
    after_ts = all_events[0]["ts"]

    # Page starting after the first event timestamp
    page = snapshot_paged(log, limit=2, after_ts=after_ts)
    events = page["events"]
    assert len(events) == 2
    assert events[0]["id"] < events[-1]["id"]
    assert page["next_after_id"] is not None
