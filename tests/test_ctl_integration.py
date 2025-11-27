# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Integration tests for CTL v1 - full end-to-end scenarios."""

from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.core.concept_ops_compiler import compile_concept_ops
from pmm.core.concept_ontology import seed_ctl_ontology
from pmm.retrieval.vector import select_by_concepts
from pmm.runtime.context_utils import render_concept_context
from pmm.core.concept_metrics import check_concept_health, compute_concept_metrics
from tests.ctl_payloads import base_ontology_payload


def test_ctl_full_workflow():
    """Test complete CTL workflow: seed → define → bind → retrieve → render."""
    log = EventLog(":memory:")

    # Step 1: Seed ontology
    seed_ctl_ontology(log, base_ontology_payload())

    # Verify ontology was seeded
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())
    assert len(cg.concepts) > 40  # Should have 41+ concepts

    # Step 2: Add some events
    e1 = log.append(kind="user_message", content="discussing stability", meta={})
    e2 = log.append(kind="assistant_message", content="about coherence", meta={})

    # Step 3: Bind events to concepts
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.system_maturity"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.coherence"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Step 4: Rebuild and verify
    cg.rebuild(log.read_all())

    # Step 5: Concept-seeded retrieval
    ids = select_by_concepts(
        concept_tokens=["topic.system_maturity"],
        concept_graph=cg,
        events=log.read_all(),
        limit=10,
    )
    assert e1 in ids

    # Step 6: Render concept context
    context = render_concept_context(log, limit=5)
    assert "Concept Context:" in context
    assert "topic." in context

    # Step 7: Check health
    health = check_concept_health(log)
    assert health["total_concepts"] > 40
    # With many concepts and few bindings, health score will be low (many gaps)
    assert health["health_score"] >= 0.0  # Just check it's computed


def test_ctl_determinism_across_rebuilds():
    """Test CTL is deterministic across multiple rebuilds."""
    log = EventLog(":memory:")

    # Seed ontology
    seed_ctl_ontology(log, base_ontology_payload())

    # Add events and bindings
    e1 = log.append(kind="user_message", content="test1", meta={})
    e2 = log.append(kind="user_message", content="test2", meta={})

    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.stability_metrics"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.stability_metrics"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    events = log.read_all()

    # Build ConceptGraph 3 times
    results = []
    for _ in range(3):
        cg = ConceptGraph(log)
        cg.rebuild(events)

        stats = cg.stats()
        concept_list = sorted(cg.concepts.keys())
        bindings = cg.events_for_concept("topic.stability_metrics")

        results.append((stats, concept_list, bindings))

    # All results should be identical
    assert results[0] == results[1] == results[2]


def _test_ctl_concept_ops_compilation():
    """Test concept_ops compilation from structured JSON."""
    log = EventLog(":memory:")

    # Seed ontology first
    seed_ctl_ontology(log, base_ontology_payload())

    # Create an assistant message with concept_ops
    e1 = log.append(kind="user_message", content="test", meta={})

    # First, just define a new concept
    concept_ops_define = {
        "define": [
            {
                "token": "topic.test_new",
                "concept_kind": "topic",
                "definition": "a new test topic",
                "attributes": {},
                "version": "1.0",
            }
        ],
        "bind_events": [],
        "relate": [],
        "aliases": [],
    }

    # Compile concept_ops
    events_added = compile_concept_ops(log, concept_ops_define)
    assert events_added > 0

    # Verify compilation
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())

    # Should have the new concept
    assert "topic.test_new" in cg.concepts

    # Now bind and relate
    concept_ops_bind = {
        "define": [],
        "bind_events": [
            {
                "event_id": e1,
                "tokens": ["topic.test_new"],
                "relation": "discusses",
                "weight": 1.0,
            }
        ],
        "relate": [
            {
                "from": "topic.test_new",
                "to": "topic.system_maturity",
                "relation": "relates_to",
                "weight": 1.0,
            }
        ],
        "aliases": [],
    }

    compile_concept_ops(log, concept_ops_bind)
    cg.rebuild(log.read_all())

    # Should have the binding
    events = cg.events_for_concept("topic.test_new")
    assert e1 in events

    # Should have the relation
    neighbors = cg.neighbors("topic.test_new")
    assert "topic.system_maturity" in neighbors


def test_ctl_idempotency():
    """Test CTL operations are idempotent."""
    log = EventLog(":memory:")

    # Define a concept twice with same content
    content = '{"token":"topic.test","concept_kind":"topic","definition":"test","attributes":{},"version":"1.0"}'

    log.append(kind="concept_define", content=content, meta={})
    log.append(kind="concept_define", content=content, meta={})

    # Should only have one concept definition
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())

    # The second define should update (replace) the first
    assert "topic.test" in cg.concepts
    history = cg.get_history("topic.test")
    assert len(history) == 2  # Both versions tracked in history


def test_ctl_with_vector_retrieval():
    """Test CTL integration with vector retrieval."""
    log = EventLog(":memory:")

    # Seed ontology
    seed_ctl_ontology(log, base_ontology_payload())

    # Create events
    e1 = log.append(kind="user_message", content="stability discussion", meta={})
    e2 = log.append(kind="user_message", content="coherence analysis", meta={})
    e3 = log.append(kind="user_message", content="more stability", meta={})

    # Bind to concepts
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.stability_metrics"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.coherence"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e3},"tokens":["topic.stability_metrics"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Rebuild ConceptGraph
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())

    # Concept-seeded retrieval
    ids = select_by_concepts(
        concept_tokens=["topic.stability_metrics"],
        concept_graph=cg,
        events=log.read_all(),
        limit=10,
    )

    # Should get both stability events
    assert set(ids) == {e1, e3}
    # Should be in descending order (most recent first)
    assert ids == [e3, e1]


def test_ctl_metrics_integration():
    """Test concept metrics integration."""
    log = EventLog(":memory:")

    # Seed ontology
    seed_ctl_ontology(log, base_ontology_payload())

    # Create events and bindings
    events = []
    for i in range(5):
        eid = log.append(kind="user_message", content=f"msg {i}", meta={})
        events.append(eid)

    # Bind multiple events to governance concepts
    for eid in events[:3]:
        log.append(
            kind="concept_bind_event",
            content=f'{{"event_id":{eid},"tokens":["policy.stability_v2"],"relation":"discusses","weight":1.0}}',
            meta={},
        )

    # Bind one event to a topic
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{events[3]},"tokens":["topic.coherence"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Compute metrics
    metrics = compute_concept_metrics(log)

    # Should have usage counts
    assert metrics["concepts_used"]["policy.stability_v2"] == 3
    assert metrics["concepts_used"]["topic.coherence"] == 1

    # topic.coherence should be a gap (< 2 refs)
    assert "topic.coherence" in metrics["concept_gaps"]

    # Check health
    health = check_concept_health(log)
    assert health["total_concepts"] > 40
    assert health["governance_concept_count"] > 0
    assert health["gap_count"] > 0  # Many concepts with no bindings


def test_ctl_replay_safety():
    """Test CTL is replay-safe (rebuild equals incremental sync)."""
    log = EventLog(":memory:")

    # Seed ontology
    seed_ctl_ontology(log, base_ontology_payload())

    # Add events and bindings incrementally
    e1 = log.append(kind="user_message", content="test1", meta={})
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.coherence"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    e2 = log.append(kind="user_message", content="test2", meta={})
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.coherence"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Method 1: Full rebuild
    cg1 = ConceptGraph(log)
    cg1.rebuild(log.read_all())

    # Method 2: Incremental sync
    cg2 = ConceptGraph(log)
    for event in log.read_all():
        cg2.sync(event)

    # Results should be identical
    assert cg1.stats() == cg2.stats()
    assert sorted(cg1.concepts.keys()) == sorted(cg2.concepts.keys())
    assert cg1.events_for_concept("topic.coherence") == cg2.events_for_concept(
        "topic.coherence"
    )


def test_ctl_context_rendering_determinism():
    """Test concept context rendering is deterministic."""
    log = EventLog(":memory:")

    # Seed ontology
    seed_ctl_ontology(log, base_ontology_payload())

    # Add bindings
    e1 = log.append(kind="user_message", content="test", meta={})
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.system_maturity","policy.stability_v2"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Render multiple times
    contexts = [render_concept_context(log, limit=5) for _ in range(3)]

    # All should be identical
    assert contexts[0] == contexts[1] == contexts[2]
