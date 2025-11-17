# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_concept_ops_compiler.py
"""Tests for concept_ops compiler."""


from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.core.concept_ops_compiler import (
    ConceptOpsCompiler,
    compile_assistant_message_concepts,
)


class TestConceptOpsCompiler:
    def test_compile_defines(self):
        log = EventLog()
        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        concept_ops = {
            "define": [
                {
                    "token": "test.new_concept",
                    "concept_kind": "test",
                    "definition": "A new test concept",
                    "attributes": {"priority": 0.8},
                    "version": 1,
                }
            ]
        }

        events_added = compiler.compile_concept_ops(concept_ops, source="test")
        assert events_added == 1

        # Rebuild graph and check
        graph.rebuild()
        concept_def = graph.get_definition("test.new_concept")
        assert concept_def is not None
        assert concept_def.definition == "A new test concept"

    def test_compile_defines_idempotency(self):
        log = EventLog()
        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        concept_ops = {
            "define": [
                {
                    "token": "test.concept",
                    "concept_kind": "test",
                    "definition": "Test",
                    "attributes": {},
                    "version": 1,
                }
            ]
        }

        # First compilation
        events1 = compiler.compile_concept_ops(concept_ops, source="test")
        assert events1 == 1

        # Rebuild graph
        graph.rebuild()

        # Second compilation with identical payload
        events2 = compiler.compile_concept_ops(concept_ops, source="test")
        assert events2 == 0  # Should skip duplicate

    def test_compile_aliases(self):
        log = EventLog()
        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        # First define a concept
        concept_ops1 = {
            "define": [
                {
                    "token": "test.canonical",
                    "concept_kind": "test",
                    "definition": "Canonical concept",
                }
            ]
        }
        compiler.compile_concept_ops(concept_ops1, source="test")
        graph.rebuild()

        # Then create alias
        concept_ops2 = {
            "aliases": [
                {
                    "from": "test.alias",
                    "to": "test.canonical",
                    "reason": "Alternative name",
                }
            ]
        }

        events_added = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events_added == 1

        # Rebuild and check alias resolution
        graph.rebuild()
        assert graph.canonical_token("test.alias") == "test.canonical"

    def test_compile_aliases_idempotency(self):
        log = EventLog()
        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        # Define concept
        concept_ops1 = {
            "define": [{"token": "test.A", "concept_kind": "test", "definition": "A"}]
        }
        compiler.compile_concept_ops(concept_ops1, source="test")
        graph.rebuild()

        # Create alias
        concept_ops2 = {"aliases": [{"from": "test.B", "to": "test.A"}]}

        events1 = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events1 == 1

        graph.rebuild()

        # Try to create same alias again
        events2 = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events2 == 0  # Should skip

    def test_compile_bind_events(self):
        log = EventLog()

        # Create some events to bind to
        msg_id1 = log.append(kind="user_message", content="Test 1", meta={})
        msg_id2 = log.append(kind="user_message", content="Test 2", meta={})

        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        # Define concepts first
        concept_ops1 = {
            "define": [
                {"token": "topic.A", "concept_kind": "topic", "definition": "Topic A"},
                {"token": "topic.B", "concept_kind": "topic", "definition": "Topic B"},
            ]
        }
        compiler.compile_concept_ops(concept_ops1, source="test")
        graph.rebuild()

        # Bind concepts to events
        concept_ops2 = {
            "bind_events": [
                {
                    "event_id": msg_id1,
                    "tokens": ["topic.A", "topic.B"],
                    "relation": "mention",
                },
                {
                    "event_id": msg_id2,
                    "tokens": ["topic.A"],
                    "relation": "evidence",
                },
            ]
        }

        events_added = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events_added == 2

        # Rebuild and check bindings
        graph.rebuild()

        concepts1 = graph.concepts_for_event(msg_id1)
        assert set(concepts1) == {"topic.A", "topic.B"}

        concepts2 = graph.concepts_for_event(msg_id2)
        assert "topic.A" in concepts2

    def test_compile_bind_events_idempotency(self):
        log = EventLog()
        msg_id = log.append(kind="user_message", content="Test", meta={})

        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        # Define concept
        concept_ops1 = {
            "define": [{"token": "topic.A", "concept_kind": "topic", "definition": "A"}]
        }
        compiler.compile_concept_ops(concept_ops1, source="test")
        graph.rebuild()

        # Bind concept to event
        concept_ops2 = {
            "bind_events": [
                {"event_id": msg_id, "tokens": ["topic.A"], "relation": "mention"}
            ]
        }

        events1 = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events1 == 1

        graph.rebuild()

        # Try to bind same concept again
        events2 = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events2 == 0  # Should skip

    def test_compile_bind_events_skips_nonexistent_events(self):
        log = EventLog()
        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        # Try to bind to nonexistent event
        concept_ops = {
            "bind_events": [
                {"event_id": 99999, "tokens": ["topic.A"], "relation": "mention"}
            ]
        }

        events_added = compiler.compile_concept_ops(concept_ops, source="test")
        assert events_added == 0  # Should skip

    def test_compile_relates(self):
        log = EventLog()
        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        # Define concepts first
        concept_ops1 = {
            "define": [
                {"token": "topic.A", "concept_kind": "topic", "definition": "A"},
                {"token": "topic.B", "concept_kind": "topic", "definition": "B"},
            ]
        }
        compiler.compile_concept_ops(concept_ops1, source="test")
        graph.rebuild()

        # Create relationships
        concept_ops2 = {
            "relate": [
                {
                    "from": "topic.A",
                    "to": "topic.B",
                    "relation": "influences",
                    "weight": 0.8,
                }
            ]
        }

        events_added = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events_added == 1

        # Rebuild and check relationship
        graph.rebuild()
        neighbors = graph.outgoing_neighbors("topic.A", relation="influences")
        assert "topic.B" in neighbors

    def test_compile_relates_idempotency(self):
        log = EventLog()
        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        # Define concepts
        concept_ops1 = {
            "define": [
                {"token": "topic.A", "concept_kind": "topic", "definition": "A"},
                {"token": "topic.B", "concept_kind": "topic", "definition": "B"},
            ]
        }
        compiler.compile_concept_ops(concept_ops1, source="test")
        graph.rebuild()

        # Create relationship
        concept_ops2 = {
            "relate": [{"from": "topic.A", "to": "topic.B", "relation": "influences"}]
        }

        events1 = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events1 == 1

        graph.rebuild()

        # Try to create same relationship again
        events2 = compiler.compile_concept_ops(concept_ops2, source="test")
        assert events2 == 0  # Should skip

    def test_compile_all_operations_together(self):
        log = EventLog()
        msg_id = log.append(kind="user_message", content="Test", meta={})

        graph = ConceptGraph(log)
        graph.rebuild()

        compiler = ConceptOpsCompiler(log, graph)

        # Comprehensive concept_ops with all operation types
        concept_ops = {
            "define": [
                {"token": "topic.X", "concept_kind": "topic", "definition": "Topic X"},
                {"token": "topic.Y", "concept_kind": "topic", "definition": "Topic Y"},
            ],
            "aliases": [{"from": "topic.X_alias", "to": "topic.X"}],
            "bind_events": [
                {
                    "event_id": msg_id,
                    "tokens": ["topic.X", "topic.Y"],
                    "relation": "mention",
                }
            ],
            "relate": [{"from": "topic.X", "to": "topic.Y", "relation": "influences"}],
        }

        events_added = compiler.compile_concept_ops(concept_ops, source="test")
        assert events_added == 5  # 2 defines + 1 alias + 1 bind + 1 relate

        # Rebuild and verify all operations
        graph.rebuild()

        assert graph.get_definition("topic.X") is not None
        assert graph.get_definition("topic.Y") is not None
        assert graph.canonical_token("topic.X_alias") == "topic.X"
        assert set(graph.concepts_for_event(msg_id)) == {"topic.X", "topic.Y"}
        assert "topic.Y" in graph.outgoing_neighbors("topic.X", relation="influences")


class TestAssistantMessageConceptCompilation:
    def test_compile_assistant_message_concepts(self):
        log = EventLog()

        # Create assistant message with concept_ops in meta
        assistant_msg_meta = {
            "source": "assistant",
            "concept_ops": {
                "define": [
                    {
                        "token": "topic.new_insight",
                        "concept_kind": "topic",
                        "definition": "A new insight from reflection",
                    }
                ]
            },
        }

        msg_id = log.append(
            kind="assistant_message",
            content="I've discovered a new insight...",
            meta=assistant_msg_meta,
        )

        graph = ConceptGraph(log)
        graph.rebuild()

        # Compile concepts from the assistant message
        assistant_event = log.get(msg_id)
        events_added = compile_assistant_message_concepts(log, graph, assistant_event)

        assert events_added == 1

        # Rebuild and verify
        graph.rebuild()
        concept_def = graph.get_definition("topic.new_insight")
        assert concept_def is not None
        assert concept_def.definition == "A new insight from reflection"

    def test_compile_assistant_message_no_concept_ops(self):
        log = EventLog()

        # Assistant message without concept_ops
        msg_id = log.append(
            kind="assistant_message",
            content="Regular message",
            meta={"source": "assistant"},
        )

        graph = ConceptGraph(log)
        graph.rebuild()

        assistant_event = log.get(msg_id)
        events_added = compile_assistant_message_concepts(log, graph, assistant_event)

        assert events_added == 0

    def test_compile_non_assistant_message(self):
        log = EventLog()

        msg_id = log.append(kind="user_message", content="User message", meta={})

        graph = ConceptGraph(log)
        graph.rebuild()

        user_event = log.get(msg_id)
        events_added = compile_assistant_message_concepts(log, graph, user_event)

        assert events_added == 0  # Should skip non-assistant messages
