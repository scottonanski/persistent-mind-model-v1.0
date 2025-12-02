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
    # Bind to sticky concept so it is selectable
    bind_payload = json.dumps(
        {"event_id": e_msg, "tokens": ["user.identity"], "relation": "relevant_to"},
        sort_keys=True,
        separators=(",", ":"),
    )
    log.append(kind="concept_bind_event", content=bind_payload, meta={})

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


def test_retrieval_pipeline_forced_concepts_precede_vector():
    """Force critical CTL concepts into context before vector pruning."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)

    # Define an identity concept and bind it to an early event.
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "identity.user",
                "concept_kind": "identity",
                "definition": "user identity",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )
    identity_event = log.append(
        kind="user_message",
        content="I am the user",
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {
                "event_id": identity_event,
                "tokens": ["identity.user"],
                "relation": "relevant_to",
            }
        ),
        meta={},
    )

    # A later event that will win vector similarity without forced inclusion.
    log.append(kind="user_message", content="unique keyword target", meta={})

    mg.rebuild(log.read_all())
    cg.rebuild(log.read_all())

    config = RetrievalConfig(
        always_include_concepts=["identity.user"],
        sticky_concepts=[],
        limit_total_events=1,
        limit_vector_events=1,
        enable_vector_search=True,
        force_concept_prefixes=["identity."],
        force_concept_limit=3,
    )

    res = run_retrieval_pipeline(
        query_text="unique keyword target",
        eventlog=log,
        concept_graph=cg,
        meme_graph=mg,
        config=config,
    )

    # The identity-bound event must be present even though vector would favor the later event.
    assert res.event_ids[0] == identity_event


def test_retrieval_pipeline_bucket_priority_respects_limit():
    """Pinned identity + concept events should survive limit before vector/residual."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)

    # Define concepts
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "identity.user",
                "concept_kind": "identity",
                "definition": "user identity",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "topic.test",
                "concept_kind": "topic",
                "definition": "test topic",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )

    # Identity-bound event (will be forced/pinned)
    identity_event = log.append(
        kind="user_message",
        content="I am the user",
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {
                "event_id": identity_event,
                "tokens": ["identity.user"],
                "relation": "relevant_to",
            }
        ),
        meta={},
    )

    # Concept-bound event
    concept_event = log.append(
        kind="assistant_message",
        content="About the test topic",
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {
                "event_id": concept_event,
                "tokens": ["topic.test"],
                "relation": "relates_to",
            }
        ),
        meta={},
    )

    # A later vector-eligible event that should be trimmed by the limit
    vector_event = log.append(
        kind="user_message",
        content="unique keyword target",
        meta={},
    )

    mg.rebuild(log.read_all())
    cg.rebuild(log.read_all())

    config = RetrievalConfig(
        always_include_concepts=["identity.user", "topic.test"],
        sticky_concepts=[],
        limit_total_events=2,
        limit_vector_events=1,
        enable_vector_search=True,
        force_concept_prefixes=["identity."],
        force_concept_limit=3,
    )

    res = run_retrieval_pipeline(
        query_text="unique keyword target",
        eventlog=log,
        concept_graph=cg,
        meme_graph=mg,
        config=config,
    )

    # Should include pinned identity + concept-bound event; vector event excluded due to cap.
    assert identity_event in res.event_ids
    assert concept_event in res.event_ids
    assert vector_event not in res.event_ids


def test_retrieval_pipeline_pins_summary_and_evidence_tail():
    """Recent summary/lifetime_memory should be pinned with evidence tail included."""
    log = EventLog(":memory:")
    mg = MemeGraph(log)
    cg = ConceptGraph(log)

    # Older evidence
    ev1 = log.append(kind="user_message", content="old fact A", meta={})
    ev2 = log.append(kind="assistant_message", content="old fact B", meta={})

    # Summary pointing to evidence ids
    summary_id = log.append(
        kind="summary_update",
        content="Summary of past events",
        meta={"sample_ids": [ev1, ev2]},
    )

    # A newer message to compete for space
    log.append(kind="user_message", content="recent chatter", meta={})

    mg.rebuild(log.read_all())
    cg.rebuild(log.read_all())

    config = RetrievalConfig(
        limit_total_events=3,
        enable_vector_search=False,
        summary_event_kinds=["summary_update"],
        summary_pin_limit=1,
        include_summary_events=True,
    )

    res = run_retrieval_pipeline(
        query_text="",
        eventlog=log,
        concept_graph=cg,
        meme_graph=mg,
        config=config,
    )

    # Summary is pinned, evidence tail included even if old; recent may be trimmed if needed.
    assert summary_id in res.event_ids
    assert ev1 in res.event_ids
    assert ev2 in res.event_ids
