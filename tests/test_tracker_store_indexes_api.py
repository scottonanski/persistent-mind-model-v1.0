from pmm.commitments.tracker import api as tracker_api


def _ev(kind, id, ts=None, **meta):
    return {"kind": kind, "id": id, "ts": ts, "meta": meta}


def test_store_and_indexes_basic():
    events = [
        _ev("commitment_open", 1, 1.0, cid="c1", text="Task 1"),
        _ev("commitment_open", 2, 2.0, cid="c2", text="Task 2"),
        _ev("commitment_close", 3, 3.0, cid="c1"),
        _ev("commitment_expire", 4, 4.0, cid="c2", reason="timeout"),
        _ev("commitment_open", 5, 5.0, cid="c3", text="Task 3"),
        _ev("commitment_snooze", 6, 6.0, cid="c3", until_tick=10),
        _ev("commitment_due", 7, 7.0, cid="c3", due_epoch=999999),
    ]

    store = tracker_api.snapshot(events)
    assert "c3" in store.open and "c1" not in store.open and "c2" not in store.open
    assert store.closed.get("c1") is not None
    assert store.expired.get("c2") is not None
    assert store.snoozed_until.get("c3") == 10
    assert "c3" in store.due_emitted


def test_window_queries_by_id_and_ts():
    events = [
        _ev("commitment_open", 10, 100.0, cid="a"),
        _ev("commitment_open", 11, 110.0, cid="b"),
        _ev("commitment_close", 12, 120.0, cid="a"),
        _ev("commitment_expire", 13, 130.0, cid="b"),
        _ev("commitment_open", 14, 140.0, cid="c"),
    ]

    # Opens within id window
    id_window_opens = tracker_api.opens_within(events, since_id=11, until_id=13)
    kinds = [e["kind"] for e in id_window_opens]
    assert kinds == ["commitment_open"]
    assert id_window_opens[0]["meta"]["cid"] == "b"

    # Closes within ts window
    ts_window_closes = tracker_api.closes_within(events, since_ts=115.0, until_ts=125.0)
    assert len(ts_window_closes) == 1
    assert ts_window_closes[0]["meta"]["cid"] == "a"

    # Effective open at id boundary (before eid 12)
    eff_open = tracker_api.open_effective_at(events, until_id=11)
    assert set(eff_open.keys()) == {"a", "b"}
