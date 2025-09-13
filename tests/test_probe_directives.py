from pmm.api.probe import render_directives, snapshot_directives


def _fake_evlog(events):
    class _E:
        def read_all(self):
            return events

    return _E()


def test_snapshot_directives_limits_and_order():
    events = [
        {
            "kind": "autonomy_directive",
            "id": 11,
            "ts": "2025-01-02T00:00:01Z",
            "content": "B",
            "meta": {"source": "reply", "origin_eid": 1},
        },
        {
            "kind": "autonomy_directive",
            "id": 10,
            "ts": "2025-01-01T00:00:00Z",
            "content": "A",
            "meta": {"source": "reflection", "origin_eid": 2},
        },
        {
            "kind": "autonomy_directive",
            "id": 12,
            "ts": "2025-01-03T00:00:00Z",
            "content": "A",
            "meta": {"source": "reply", "origin_eid": 3},
        },
    ]
    rows = snapshot_directives(_fake_evlog(events))
    # Sorted by first_seen_ts/id via projection.build_directives
    assert [r["content"] for r in rows] == ["A", "B"]
    assert rows[0]["seen_count"] == 2
    assert rows[0]["sources"] == ["reflection", "reply"]

    top1 = snapshot_directives(_fake_evlog(events), limit=1)
    assert [r["content"] for r in top1] == ["A"]


def test_render_directives_layout_is_stable():
    rows = [
        {
            "content": "keep replies concise.",
            "seen_count": 2,
            "sources": ["reflection", "reply"],
            "first_seen_id": 10,
            "last_seen_id": 12,
        },
    ]
    out = render_directives(rows)
    assert "keep replies concise." in out
    assert "reflection,reply" in out
    assert "first_id" in out and "last_id" in out
