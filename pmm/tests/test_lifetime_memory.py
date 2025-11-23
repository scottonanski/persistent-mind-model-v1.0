# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

import json

from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.retrieval.pipeline import RetrievalConfig, run_retrieval_pipeline
from pmm.runtime.lifetime_memory import maybe_append_lifetime_memory


def test_lifetime_memory_chunk_emitted_and_embedded() -> None:
    log = EventLog(":memory:")
    cg = ConceptGraph(log)
    log.register_listener(cg.sync)

    # Generate enough messages to cross the threshold (small for test).
    for i in range(25):
        log.append(
            kind="user_message",
            content=f"user note {i}",
            meta={"role": "user"},
        )
        log.append(
            kind="assistant_message",
            content=f"assistant reply {i}",
            meta={"role": "assistant"},
        )

    eid = maybe_append_lifetime_memory(log, cg, chunk_size=20, message_samples=5)
    assert eid is not None

    event = log.get(eid)
    assert event is not None
    meta = event.get("meta") or {}
    assert int(meta.get("covered_until", 0)) >= 20
    assert len(meta.get("sample_ids", [])) <= 5

    embeddings = [e for e in log.read_all() if e.get("kind") == "embedding_add"]
    assert any(json.loads(e["content"])["event_id"] == eid for e in embeddings)


def test_retrieval_uses_lifetime_memory_for_old_events() -> None:
    log = EventLog(":memory:")
    cg = ConceptGraph(log)
    mg = MemeGraph(log)
    log.register_listener(cg.sync)
    log.register_listener(mg.add_event)

    # Create older events containing a unique topic.
    for i in range(30):
        text = "ancient meeting about saturn" if i == 3 else f"old note {i}"
        log.append(
            kind="user_message",
            content=text,
            meta={"role": "user"},
        )
        log.append(
            kind="assistant_message",
            content=f"ack {i}",
            meta={"role": "assistant"},
        )

    # Summarize the old span with a small chunk size to make the test fast.
    chunk_id = maybe_append_lifetime_memory(log, cg, chunk_size=20, message_samples=6)
    assert chunk_id is not None

    # Add newer chatter so the old events fall outside the recent tail window.
    for i in range(15):
        log.append(
            kind="user_message",
            content=f"recent noise {i}",
            meta={"role": "user"},
        )

    cfg = RetrievalConfig()
    cfg.recent_event_tail = 10  # Limit recent window to force summary usage
    cfg.limit_total_events = 40
    result = run_retrieval_pipeline(
        query_text="saturn meeting",
        eventlog=log,
        concept_graph=cg,
        meme_graph=mg,
        config=cfg,
    )

    selected = [log.get(eid) for eid in result.event_ids]
    contents = [e.get("content", "") for e in selected if e]
    assert any("saturn" in c for c in contents)
