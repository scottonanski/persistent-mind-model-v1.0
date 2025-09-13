from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import Runtime
from pmm.llm.factory import LLMConfig
from pmm.runtime.recall import suggest_recall


def _mk_runtime(tmp_path: str) -> tuple[Runtime, EventLog]:
    db = tmp_path
    log = EventLog(db)
    cfg = LLMConfig(
        provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
    )
    rt = Runtime(cfg, log)
    return rt, log


def test_recall_semantic_prefers_closest_and_ordering(monkeypatch, tmp_path):
    # Setup runtime and log
    db = tmp_path / "sem1.db"
    rt, log = _mk_runtime(str(db))

    # Create two prior events whose embeddings we will index in the side table
    eid1 = log.append(kind="note", content="Alpha topic one", meta={})
    eid2 = log.append(kind="note", content="Beta topic two", meta={})

    # Insert embeddings for eid1 and eid2 into side table: v1 is closer to query
    import struct

    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    assert log.insert_embedding_row(
        eid=eid1, digest="d1", embedding_blob=struct.pack("<3f", *v1)
    )
    assert log.insert_embedding_row(
        eid=eid2, digest="d2", embedding_blob=struct.pack("<3f", *v2)
    )

    # Monkeypatch embedding compute to return query vector near v1
    monkeypatch.setattr("pmm.runtime.embeddings.compute_embedding", lambda s: v1)

    # Monkeypatch chat.generate to return a deterministic reply
    monkeypatch.setattr(rt.chat, "generate", lambda msgs, **kw: "Discuss alpha vector.")

    # Call handle_user which triggers recall_suggest before response
    rt.handle_user("Hi")

    evs = log.read_all()
    # Ensure recall_suggest appears before response
    kinds = [e.get("kind") for e in evs]
    assert "recall_suggest" in kinds and "response" in kinds
    ridx = kinds.index("recall_suggest")
    resp_idx = kinds.index("response")
    assert ridx < resp_idx

    rec = evs[ridx]
    suggs = (rec.get("meta") or {}).get("suggestions") or []
    assert len(suggs) >= 1
    # The first suggestion should be the eid with the closer embedding (eid1)
    assert int(suggs[0]["eid"]) == int(eid1)


def test_recall_semantic_absent_falls_back(monkeypatch, tmp_path):
    # Setup runtime and log
    db = tmp_path / "sem2.db"
    rt, log = _mk_runtime(str(db))

    # Build some prior events with token-overlap so baseline recall has candidates
    log.append(kind="note", content="Project Apollo launch planning", meta={})
    log.append(kind="note", content="Cooking pasta with tomato sauce", meta={})

    # Simulate absent semantic: ensure side table empty (no inserts) and monkeypatch compute_embedding to None
    monkeypatch.setattr("pmm.runtime.embeddings.compute_embedding", lambda s: None)

    # Deterministic reply
    reply_text = "Apollo mission planning update"
    monkeypatch.setattr(rt.chat, "generate", lambda msgs, **kw: reply_text)

    # Compute baseline suggestions directly using recall on events prior to reply
    evs_pre = log.read_all()
    baseline = suggest_recall(evs_pre, reply_text, max_items=3)

    # Run handle_user which should emit recall_suggest before response
    rt.handle_user("Hi")

    evs = log.read_all()
    kinds = [e.get("kind") for e in evs]
    assert "recall_suggest" in kinds and "response" in kinds
    ridx = kinds.index("recall_suggest")
    resp_idx = kinds.index("response")
    assert ridx < resp_idx

    rec = evs[ridx]
    suggs = (rec.get("meta") or {}).get("suggestions") or []
    # Fallback path should match baseline count/order for the first element at least
    assert len(suggs) >= 1 and len(baseline) >= 1
    assert int(suggs[0]["eid"]) == int(baseline[0]["eid"])  # stable top-1
