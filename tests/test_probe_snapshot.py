from pmm.api.probe import enrich_snapshot_with_directives


def _fake_evlog(events):
    class _E:
        def read_all(self):
            return events

    return _E()


def test_enrich_snapshot_adds_directives_top():
    base = {"identity": {"name": "Unit"}}
    events = [
        {
            "kind": "autonomy_directive",
            "id": 1,
            "ts": "2025-01-01T00:00:00Z",
            "content": "Do X",
            "meta": {"source": "reply"},
        }
    ]
    snap = enrich_snapshot_with_directives(base, _fake_evlog(events), top_k=3)
    assert "identity" in snap and snap["identity"]["name"] == "Unit"
    assert "directives" in snap
    assert snap["directives"]["count"] == 1
    assert snap["directives"]["top"][0]["content"] == "Do X"
