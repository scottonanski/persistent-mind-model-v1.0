from pmm.storage.eventlog import EventLog


def test_read_tail_returns_newest_n_in_ascending_order(tmp_path):
    db = tmp_path / "pmm.db"
    evlog = EventLog(str(db))
    # append 1..10
    for i in range(1, 11):
        evlog.append(kind="k", content=str(i), meta={})
    tail = evlog.read_tail(limit=3)
    ids = [e["id"] for e in tail]
    contents = [e["content"] for e in tail]
    assert contents == ["8", "9", "10"]  # ascending within slice
    assert ids == sorted(ids)
