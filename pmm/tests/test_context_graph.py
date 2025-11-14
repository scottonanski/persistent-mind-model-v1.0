# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_context_graph.py
"""Tests for ContextGraph projection."""


from pmm.context.context_graph import ContextGraph
from pmm.context.context_query import (
    get_children,
    get_events_for_thread,
    get_events_with_tag,
)
from pmm.context.semantic_tagger import extract_semantic_tags


def test_extract_semantic_tags():
    """Test semantic tag extraction using structured parsers."""
    # Commitment event
    commit_event = {
        "id": 1,
        "kind": "assistant_message",
        "content": "I will do this.\nCOMMIT: task1",
    }
    assert extract_semantic_tags(commit_event) == ["commitment"]

    # Claim event
    claim_event = {
        "id": 2,
        "kind": "assistant_message",
        "content": 'CLAIM:memory={"type": "short_term"}',
    }
    assert extract_semantic_tags(claim_event) == ["claim"]

    # Reflection event
    reflect_event = {
        "id": 3,
        "kind": "reflection",
        "content": "Reflected on outcomes.",
    }
    assert extract_semantic_tags(reflect_event) == ["reflection"]

    # Plain event
    plain_event = {
        "id": 4,
        "kind": "user_message",
        "content": "Hello",
    }
    assert extract_semantic_tags(plain_event) == []


def test_context_graph_rebuild_and_incremental():
    """Test that rebuild and incremental builds produce identical results."""
    # In-memory event log
    events = [
        {
            "id": 1,
            "kind": "user_message",
            "content": "Start thread",
            "context": {"thread_id": "thread1"},
        },
        {
            "id": 2,
            "kind": "assistant_message",
            "content": "Response\nCOMMIT: task",
            "context": {"thread_id": "thread1", "parent_event_id": 1},
        },
        {
            "id": 3,
            "kind": "reflection",
            "content": "Reflection",
            "context": {"thread_id": "thread1", "parent_event_id": 2},
        },
    ]

    # Mock eventlog
    class MockEventLog:
        def read_all(self):
            return events

    eventlog = MockEventLog()
    graph = ContextGraph(eventlog)

    # Rebuild from all
    graph.rebuild(events)

    # Incremental build
    graph2 = ContextGraph(eventlog)
    for event in events:
        graph2.add_event(event)

    # Should be identical
    assert graph.threads == graph2.threads
    assert graph.children == graph2.children
    assert graph.semantic_tags == graph2.semantic_tags


def test_context_queries():
    """Test basic context queries."""
    events = [
        {
            "id": 1,
            "kind": "user_message",
            "content": "Hello",
            "context": {"thread_id": "t1"},
        },
        {
            "id": 2,
            "kind": "assistant_message",
            "content": "Hi\nCOMMIT: respond",
            "context": {"thread_id": "t1", "parent_event_id": 1},
        },
        {
            "id": 3,
            "kind": "reflection",
            "content": "Good",
            "context": {"thread_id": "t2", "parent_event_id": 2},
        },
    ]

    class MockEventLog:
        def read_all(self):
            return events

    graph = ContextGraph(MockEventLog())
    graph.rebuild(events)

    # Thread queries
    assert get_events_for_thread(graph, "t1") == [1, 2]
    assert get_events_for_thread(graph, "t2") == [3]

    # Children queries
    assert get_children(graph, 1) == [2]
    assert get_children(graph, 2) == [3]

    # Tag queries
    assert get_events_with_tag(graph, "commitment") == [2]
    assert get_events_with_tag(graph, "reflection") == [3]


def test_incremental_idempotent():
    """Test that add_event is idempotent."""
    event = {
        "id": 1,
        "kind": "user_message",
        "content": "Test",
        "context": {"thread_id": "test"},
    }

    class MockEventLog:
        pass

    graph = ContextGraph(MockEventLog())
    graph.add_event(event)
    graph.add_event(event)  # Duplicate

    assert graph.get_thread_events("test") == [1]
