# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for concept context rendering."""

from pmm.core.event_log import EventLog
from pmm.runtime.context_utils import render_concept_context


def test_render_concept_context_empty():
    """Test rendering with no concepts."""
    log = EventLog(":memory:")
    result = render_concept_context(log)
    assert result == ""


def test_render_concept_context_basic():
    """Test basic concept context rendering."""
    log = EventLog(":memory:")

    # Add some events
    e1 = log.append(kind="user_message", content="stability talk", meta={})
    e2 = log.append(kind="assistant_message", content="coherence discussion", meta={})

    # Define concepts
    log.append(
        kind="concept_define",
        content='{"token":"topic.stability","concept_kind":"topic","definition":"system stability and reliability","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.coherence","concept_kind":"topic","definition":"system coherence","attributes":{},"version":"1.0"}',
        meta={},
    )

    # Bind events
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

    result = render_concept_context(log, limit=5)

    assert "Concept Context:" in result
    assert "topic.stability" in result
    assert "topic.coherence" in result
    assert "(1 refs)" in result


def test_render_concept_context_sorting():
    """Test concepts are sorted by activity."""
    log = EventLog(":memory:")

    # Create events
    events = []
    for i in range(5):
        eid = log.append(kind="user_message", content=f"msg {i}", meta={})
        events.append(eid)

    # Define concepts
    log.append(
        kind="concept_define",
        content='{"token":"topic.high_activity","concept_kind":"topic","definition":"high activity topic","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.low_activity","concept_kind":"topic","definition":"low activity topic","attributes":{},"version":"1.0"}',
        meta={},
    )

    # Bind many events to high_activity
    for eid in events[:4]:
        log.append(
            kind="concept_bind_event",
            content=f'{{"event_id":{eid},"tokens":["topic.high_activity"],"relation":"discusses","weight":1.0}}',
            meta={},
        )

    # Bind one event to low_activity
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{events[4]},"tokens":["topic.low_activity"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    result = render_concept_context(log, limit=5)

    # high_activity should appear before low_activity
    high_pos = result.find("topic.high_activity")
    low_pos = result.find("topic.low_activity")
    assert high_pos < low_pos
    assert "(4 refs)" in result
    assert "(1 refs)" in result


def test_render_concept_context_limit():
    """Test limit parameter."""
    log = EventLog(":memory:")

    # Create 5 concepts with 1 binding each
    for i in range(5):
        eid = log.append(kind="user_message", content=f"msg {i}", meta={})
        log.append(
            kind="concept_define",
            content=f'{{"token":"topic.test{i}","concept_kind":"topic","definition":"test topic {i}","attributes":{{}},"version":"1.0"}}',
            meta={},
        )
        log.append(
            kind="concept_bind_event",
            content=f'{{"event_id":{eid},"tokens":["topic.test{i}"],"relation":"discusses","weight":1.0}}',
            meta={},
        )

    # Limit to 3
    result = render_concept_context(log, limit=3)

    # Should have exactly 3 concepts (plus header line)
    lines = [line for line in result.split("\n") if line.startswith("- topic.")]
    assert len(lines) == 3


def test_render_concept_context_definition_truncation():
    """Test long definitions are truncated."""
    log = EventLog(":memory:")

    e1 = log.append(kind="user_message", content="test", meta={})

    # Define concept with very long definition
    long_def = "a" * 100
    log.append(
        kind="concept_define",
        content=f'{{"token":"topic.long","concept_kind":"topic","definition":"{long_def}","attributes":{{}},"version":"1.0"}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.long"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    result = render_concept_context(log, limit=5)

    # Should be truncated with "..."
    assert "..." in result
    # Full definition should not appear
    assert long_def not in result


def test_render_concept_context_determinism():
    """Test rendering is deterministic."""
    log = EventLog(":memory:")

    e1 = log.append(kind="user_message", content="test1", meta={})
    e2 = log.append(kind="user_message", content="test2", meta={})

    log.append(
        kind="concept_define",
        content='{"token":"topic.a","concept_kind":"topic","definition":"topic a","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.b","concept_kind":"topic","definition":"topic b","attributes":{},"version":"1.0"}',
        meta={},
    )

    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.a"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.b"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Render multiple times
    result1 = render_concept_context(log, limit=5)
    result2 = render_concept_context(log, limit=5)
    result3 = render_concept_context(log, limit=5)

    assert result1 == result2 == result3
