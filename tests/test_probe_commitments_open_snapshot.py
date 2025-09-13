from pmm.api.probe import snapshot_commitments_open


def _fake_evlog(events):
    class _E:
        def read_all(self):
            return events

    return _E()


def test_snapshot_open_filters_and_orders_newest_first():
    evs = [
        {
            "kind": "commitment_open",
            "id": 1,
            "ts": 10.0,
            "content": "Prepare release notes",
        },
        {"kind": "commitment_open", "id": 2, "ts": 11.0, "content": "Update changelog"},
        {
            "kind": "commitment_close",
            "id": 3,
            "ts": 12.0,
            "content": "Prepare release notes",
        },
        {
            "kind": "commitment_open",
            "id": 4,
            "ts": 13.0,
            "content": "Prepare release notes",
        },  # re-open
    ]
    rows = snapshot_commitments_open(_fake_evlog(evs), limit=None)
    assert [r["id"] for r in rows] == [4, 2]
    assert rows[0]["content"] == "Prepare release notes"
