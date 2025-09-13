from pmm.storage.projection import build_directives


def test_projection_dedup_counts_and_sorting():
    events = [
        {
            "id": 10,
            "ts": "2025-01-01T00:00:10Z",
            "kind": "autonomy_directive",
            "content": "Always strip boilerplate.",
            "meta": {"source": "reflection", "origin_eid": 99},
        },
        {
            "id": 12,
            "ts": "2025-01-01T00:00:12Z",
            "kind": "autonomy_directive",
            "content": "Always   strip    boilerplate.",  # extra spaces to test normalization
            "meta": {"source": "reply", "origin_eid": 105},
        },
        {
            "id": 11,
            "ts": "2025-01-01T00:00:11Z",
            "kind": "autonomy_directive",
            "content": "Never claim an identity unless adopted.",
            "meta": {"source": "reflection", "origin_eid": None},
        },
    ]

    out = build_directives(events)

    # Sorted by first_seen_ts, then first_seen_id => id=10 (Always ...) then id=11 (Never ...)
    assert [d["first_seen_id"] for d in out] == [10, 11]

    # Dedup across same content, accumulate counts and sources; last_origin_eid takes last non-null
    d0 = out[0]
    assert d0["content"] == "Always strip boilerplate."
    assert d0["seen_count"] == 2
    assert d0["sources"] == ["reflection", "reply"]
    assert d0["first_seen_id"] == 10
    assert d0["last_seen_id"] == 12
    assert d0["last_origin_eid"] == 105

    # Second directive is independent
    d1 = out[1]
    assert d1["content"] == "Never claim an identity unless adopted."
    assert d1["seen_count"] == 1
    assert d1["sources"] == ["reflection"]
    assert d1["first_seen_id"] == 11
    assert d1["last_seen_id"] == 11
