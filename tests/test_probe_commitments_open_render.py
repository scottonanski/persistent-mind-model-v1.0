from pmm.api.probe import render_commitments_open


def test_render_layout_contains_core_fields():
    rows = [
        {
            "id": 4,
            "ts": 13.0,
            "origin_eid": 42,
            "content": "Prepare release notes",
            "cid": "abc123",
        }
    ]
    out = render_commitments_open(rows)
    assert "origin_eid" in out
    assert "Prepare release notes" in out
    assert "idx | ts" in out.splitlines()[0]
