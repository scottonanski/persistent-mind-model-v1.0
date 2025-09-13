from pmm.storage.projection import build_directives_active_set


def test_active_set_scoring_and_ordering_is_deterministic():
    evs = [
        {
            "kind": "autonomy_directive",
            "id": 10,
            "payload": {
                "content": "Keep replies concise.",
                "meta": {"source": "reply"},
            },
        },
        {
            "kind": "autonomy_directive",
            "id": 11,
            "payload": {
                "content": "Prefer evidence-linked closures.",
                "meta": {"source": "reflection"},
            },
        },
        # recent repeats
        {
            "kind": "autonomy_directive",
            "id": 200,
            "payload": {
                "content": "Keep replies concise.",
                "meta": {"source": "reply"},
            },
        },
        {
            "kind": "autonomy_directive",
            "id": 201,
            "payload": {
                "content": "Keep replies concise.",
                "meta": {"source": "reflection"},
            },
        },
    ]
    rows = build_directives_active_set(evs)
    # "Keep replies concise." should rank above the other due to seen_count and recent_hits
    assert rows[0]["content"].lower().startswith("keep replies")
    # stable sorting and fields present
    assert "score" in rows[0] and "recent_hits" in rows[0]
