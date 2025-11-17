# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for concept-seeded retrieval integration."""

from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.retrieval.vector import select_by_concepts


def test_select_by_concepts_basic():
    """Test basic concept-seeded retrieval."""
    log = EventLog(":memory:")
    cg = ConceptGraph(log)

    # Create some events
    e1 = log.append(kind="user_message", content="discussing stability", meta={})
    e2 = log.append(kind="assistant_message", content="about coherence", meta={})
    e3 = log.append(kind="user_message", content="more stability talk", meta={})

    # Define concepts
    log.append(
        kind="concept_define",
        content='{"token":"topic.stability","concept_kind":"topic","definition":"system stability","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.coherence","concept_kind":"topic","definition":"system coherence","attributes":{},"version":"1.0"}',
        meta={},
    )

    # Bind events to concepts
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.stability"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.coherence"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e3},"tokens":["topic.stability"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Rebuild ConceptGraph
    cg.rebuild(log.read_all())

    # Select by stability concept
    ids = select_by_concepts(
        concept_tokens=["topic.stability"],
        concept_graph=cg,
        events=log.read_all(),
        limit=10,
    )
    assert set(ids) == {e1, e3}
    # Should be sorted descending (most recent first)
    assert ids == [e3, e1]


def test_select_by_concepts_multiple_tokens():
    """Test retrieval with multiple concept tokens."""
    log = EventLog(":memory:")
    cg = ConceptGraph(log)

    e1 = log.append(kind="user_message", content="stability", meta={})
    e2 = log.append(kind="assistant_message", content="coherence", meta={})
    e3 = log.append(kind="user_message", content="both topics", meta={})

    log.append(
        kind="concept_define",
        content='{"token":"topic.stability","concept_kind":"topic","definition":"stability","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.coherence","concept_kind":"topic","definition":"coherence","attributes":{},"version":"1.0"}',
        meta={},
    )

    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.stability"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.coherence"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e3},"tokens":["topic.stability","topic.coherence"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    cg.rebuild(log.read_all())

    # Select by both concepts - should get all three events
    ids = select_by_concepts(
        concept_tokens=["topic.stability", "topic.coherence"],
        concept_graph=cg,
        events=log.read_all(),
        limit=10,
    )
    assert set(ids) == {e1, e2, e3}
    assert ids == [e3, e2, e1]  # descending order


def test_select_by_concepts_with_relation_filter():
    """Test retrieval with relation filtering."""
    log = EventLog(":memory:")
    cg = ConceptGraph(log)

    e1 = log.append(kind="user_message", content="example of stability", meta={})
    e2 = log.append(kind="assistant_message", content="discussing stability", meta={})

    log.append(
        kind="concept_define",
        content='{"token":"topic.stability","concept_kind":"topic","definition":"stability","attributes":{},"version":"1.0"}',
        meta={},
    )

    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.stability"],"relation":"exemplifies","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.stability"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    cg.rebuild(log.read_all())

    # Filter by "exemplifies" relation
    ids = select_by_concepts(
        concept_tokens=["topic.stability"],
        concept_graph=cg,
        events=log.read_all(),
        limit=10,
        relation="exemplifies",
    )
    assert ids == [e1]

    # Filter by "discusses" relation
    ids = select_by_concepts(
        concept_tokens=["topic.stability"],
        concept_graph=cg,
        events=log.read_all(),
        limit=10,
        relation="discusses",
    )
    assert ids == [e2]


def test_select_by_concepts_with_aliases():
    """Test retrieval with concept aliases."""
    log = EventLog(":memory:")
    cg = ConceptGraph(log)

    e1 = log.append(kind="user_message", content="stability", meta={})

    log.append(
        kind="concept_define",
        content='{"token":"topic.stability","concept_kind":"topic","definition":"stability","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_alias",
        content='{"from":"topic.stable","to":"topic.stability","reason":"synonym"}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.stability"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    cg.rebuild(log.read_all())

    # Should work with alias
    ids = select_by_concepts(
        concept_tokens=["topic.stable"],
        concept_graph=cg,
        events=log.read_all(),
        limit=10,
    )
    assert ids == [e1]


def test_select_by_concepts_empty():
    """Test retrieval with no concepts."""
    log = EventLog(":memory:")
    cg = ConceptGraph(log)

    ids = select_by_concepts(
        concept_tokens=[],
        concept_graph=cg,
        events=log.read_all(),
        limit=10,
    )
    assert ids == []


def test_select_by_concepts_limit():
    """Test retrieval respects limit."""
    log = EventLog(":memory:")
    cg = ConceptGraph(log)

    # Create 5 events
    events = []
    for i in range(5):
        eid = log.append(kind="user_message", content=f"message {i}", meta={})
        events.append(eid)

    log.append(
        kind="concept_define",
        content='{"token":"topic.test","concept_kind":"topic","definition":"test","attributes":{},"version":"1.0"}',
        meta={},
    )

    # Bind all to same concept
    for eid in events:
        log.append(
            kind="concept_bind_event",
            content=f'{{"event_id":{eid},"tokens":["topic.test"],"relation":"discusses","weight":1.0}}',
            meta={},
        )

    cg.rebuild(log.read_all())

    # Limit to 3
    ids = select_by_concepts(
        concept_tokens=["topic.test"],
        concept_graph=cg,
        events=log.read_all(),
        limit=3,
    )
    assert len(ids) == 3
    # Should be most recent 3
    assert ids == events[-3:][::-1]  # last 3, reversed


def test_select_by_concepts_determinism():
    """Test retrieval is deterministic across rebuilds."""
    log = EventLog(":memory:")

    e1 = log.append(kind="user_message", content="msg1", meta={})
    e2 = log.append(kind="user_message", content="msg2", meta={})
    e3 = log.append(kind="user_message", content="msg3", meta={})

    log.append(
        kind="concept_define",
        content='{"token":"topic.test","concept_kind":"topic","definition":"test","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.test"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.test"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e3},"tokens":["topic.test"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    events = log.read_all()

    # Build ConceptGraph twice
    cg1 = ConceptGraph(log)
    cg1.rebuild(events)
    ids1 = select_by_concepts(
        concept_tokens=["topic.test"],
        concept_graph=cg1,
        events=events,
        limit=10,
    )

    cg2 = ConceptGraph(log)
    cg2.rebuild(events)
    ids2 = select_by_concepts(
        concept_tokens=["topic.test"],
        concept_graph=cg2,
        events=events,
        limit=10,
    )

    assert ids1 == ids2
