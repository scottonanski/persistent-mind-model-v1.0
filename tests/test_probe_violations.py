from pmm.api.probe import render_violations, snapshot_violations


def _fake_evlog(events):
    class _E:
        def read_all(self):
            return events

    return _E()


def test_snapshot_violations_filters_and_orders_newest_first():
    events = [
        {
            "kind": "invariant_violation",
            "id": 1,
            "ts": 10.0,
            "payload": {
                "code": "TTL_OPEN_COMMITMENTS",
                "message": "expired",
                "details": {"commitment_id": "C1"},
            },
        },
        {
            "kind": "autonomy_directive",
            "id": 2,
            "ts": 11.0,
            "payload": {"content": "A", "meta": {"source": "reply"}},
        },
        {
            "kind": "invariant_violation",
            "id": 3,
            "ts": 12.0,
            "payload": {
                "code": "CANDIDATE_BEFORE_CLOSE",
                "message": "missing candidate",
                "details": {"commitment_id": "C2"},
            },
        },
    ]
    rows = snapshot_violations(_fake_evlog(events), limit=None)
    # newest first: id 3, then id 1
    assert [r["id"] for r in rows] == [3, 1]
    assert rows[0]["code"] == "CANDIDATE_BEFORE_CLOSE"
    assert rows[1]["code"] == "TTL_OPEN_COMMITMENTS"


def test_render_violations_layout_contains_core_fields():
    rows = [
        {
            "id": 3,
            "ts": 12.0,
            "code": "CANDIDATE_BEFORE_CLOSE",
            "message": "missing candidate",
            "details": {"commitment_id": "C2"},
        }
    ]
    out = render_violations(rows)
    assert "CANDIDATE_BEFORE_CLOSE" in out
    assert "missing candidate" in out
    assert "idx | code" in out.splitlines()[0]
