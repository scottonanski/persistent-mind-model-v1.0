# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for the deterministic retrieval pipeline."""

import json
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.core.concept_graph import ConceptGraph
from pmm.retrieval.pipeline import run_retrieval_pipeline, RetrievalConfig


def test_retrieval_pipeline_determinism():
    """Test that the pipeline is deterministic."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)

    # Add some events
    log.append(kind="user_message", content="hello", meta={})
    log.append(kind="assistant_message", content="hi", meta={})

    mg.rebuild(log.read_all())
    cg.rebuild(log.read_all())

    config = RetrievalConfig()

    res1 = run_retrieval_pipeline(
        query_text="hello", eventlog=log, concept_graph=cg, meme_graph=mg, config=config
    )

    res2 = run_retrieval_pipeline(
        query_text="hello", eventlog=log, concept_graph=cg, meme_graph=mg, config=config
    )

    assert res1 == res2


def test_retrieval_pipeline_concept_seeding():
    """Test that concepts seeded via config pull in relevant threads."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)

    # Define concept
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "topic.test",
                "concept_kind": "topic",
                "definition": "test",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )

    # Create thread
    cid = "thread-1"
    e_asst = log.append(
        kind="assistant_message", content="I commit.\n\nCOMMIT: X", meta={}
    )
    e_open = log.append(
        kind="commitment_open", content="req", meta={"cid": cid, "text": "X"}
    )

    # Bind concept to thread event
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {"event_id": e_open, "tokens": ["topic.test"], "relation": "relates_to"}
        ),
        meta={},
    )

    mg.rebuild(log.read_all())
    cg.rebuild(log.read_all())

    # Config asking for topic.test
    config = RetrievalConfig(
        always_include_concepts=["topic.test"], enable_vector_search=False
    )

    res = run_retrieval_pipeline(
        query_text="", eventlog=log, concept_graph=cg, meme_graph=mg, config=config
    )

    # Should find topic.test
    assert "topic.test" in res.active_concepts
    # Should find thread-1
    assert cid in res.relevant_cids
    # Should find events in thread (open and assistant)
    # Note: e_assistant is linked to e_open in MemeGraph, so concept binding on e_open
    # makes the thread relevant.
    assert e_open in res.event_ids
    assert e_asst in res.event_ids


def test_retrieval_pipeline_vector_search():
    """Test vector search integration."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)

    # Add a distinct message
    e_msg = log.append(kind="user_message", content="unique_keyword", meta={})

    mg.rebuild(log.read_all())
    cg.rebuild(log.read_all())

    config = RetrievalConfig(enable_vector_search=True)

    res = run_retrieval_pipeline(
        query_text="unique_keyword",
        eventlog=log,
        concept_graph=cg,
        meme_graph=mg,
        config=config,
    )

    assert e_msg in res.event_ids
