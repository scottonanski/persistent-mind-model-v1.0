# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_concept_graph.py
"""Tests for ConceptGraph projection."""


from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.core.concept_schemas import (
    create_concept_define_payload,
    create_concept_alias_payload,
    create_concept_bind_event_payload,
    create_concept_relate_payload,
)


class TestConceptGraphBasics:
    def test_empty_concept_graph(self):
        log = EventLog()
        graph = ConceptGraph(log)
        graph.rebuild()

        assert len(graph.concepts) == 0
        assert len(graph.aliases) == 0
        assert len(graph.concept_edges) == 0
        assert graph.stats()["total_concepts"] == 0

    def test_concept_define_adds_to_graph(self):
        log = EventLog()
        content, meta = create_concept_define_payload(
            token="identity.Echo",
            concept_kind="identity",
            definition="Primary identity facet",
        )
        log.append(kind="concept_define", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        assert len(graph.concepts) == 1
        assert "identity.Echo" in graph.concepts

        concept_def = graph.get_definition("identity.Echo")
        assert concept_def is not None
        assert concept_def.token == "identity.Echo"
        assert concept_def.concept_kind == "identity"
        assert concept_def.definition == "Primary identity facet"

    def test_multiple_concept_defines(self):
        log = EventLog()

        # Define multiple concepts
        tokens = [
            ("identity.Echo", "identity", "Primary identity"),
            ("policy.stability_v2", "policy", "Stability policy v2"),
            ("topic.system_maturity", "topic", "System maturity level"),
        ]

        for token, kind, definition in tokens:
            content, meta = create_concept_define_payload(
                token=token, concept_kind=kind, definition=definition
            )
            log.append(kind="concept_define", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        assert len(graph.concepts) == 3
        assert graph.stats()["total_concepts"] == 3
        assert graph.stats()["concepts_by_kind"]["identity"] == 1
        assert graph.stats()["concepts_by_kind"]["policy"] == 1
        assert graph.stats()["concepts_by_kind"]["topic"] == 1


class TestConceptAliases:
    def test_concept_alias_resolution(self):
        log = EventLog()

        # Define canonical concept
        content1, meta1 = create_concept_define_payload(
            token="identity.Echo",
            concept_kind="identity",
            definition="Primary identity",
        )
        log.append(kind="concept_define", content=content1, meta=meta1)

        # Create alias
        content2, meta2 = create_concept_alias_payload(
            from_token="identity.PMM",
            to_token="identity.Echo",
            reason="Unified naming",
        )
        log.append(kind="concept_alias", content=content2, meta=meta2)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Alias should resolve to canonical
        assert graph.canonical_token("identity.PMM") == "identity.Echo"
        assert graph.canonical_token("identity.Echo") == "identity.Echo"

        # get_definition should work with alias
        concept_def = graph.get_definition("identity.PMM")
        assert concept_def is not None
        assert concept_def.token == "identity.Echo"

    def test_alias_chain_resolution(self):
        log = EventLog()

        # Define canonical
        content1, meta1 = create_concept_define_payload(
            token="identity.Echo",
            concept_kind="identity",
            definition="Primary identity",
        )
        log.append(kind="concept_define", content=content1, meta=meta1)

        # Create alias chain: A -> B -> Echo
        content2, meta2 = create_concept_alias_payload(
            from_token="identity.B", to_token="identity.Echo"
        )
        log.append(kind="concept_alias", content=content2, meta=meta2)

        content3, meta3 = create_concept_alias_payload(
            from_token="identity.A", to_token="identity.B"
        )
        log.append(kind="concept_alias", content=content3, meta=meta3)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Should resolve through chain
        assert graph.canonical_token("identity.A") == "identity.Echo"
        assert graph.canonical_token("identity.B") == "identity.Echo"


class TestConceptBindings:
    def test_concept_bind_event(self):
        log = EventLog()

        # Create some events
        msg_id1 = log.append(kind="user_message", content="Test 1", meta={})
        msg_id2 = log.append(kind="user_message", content="Test 2", meta={})

        # Define concept
        content1, meta1 = create_concept_define_payload(
            token="topic.system_maturity",
            concept_kind="topic",
            definition="System maturity",
        )
        log.append(kind="concept_define", content=content1, meta=meta1)

        # Bind concept to events
        content2, meta2 = create_concept_bind_event_payload(
            event_id=msg_id1,
            tokens=["topic.system_maturity"],
            relation="mention",
        )
        log.append(kind="concept_bind_event", content=content2, meta=meta2)

        content3, meta3 = create_concept_bind_event_payload(
            event_id=msg_id2,
            tokens=["topic.system_maturity"],
            relation="evidence",
        )
        log.append(kind="concept_bind_event", content=content3, meta=meta3)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check bindings
        events = graph.events_for_concept("topic.system_maturity")
        assert len(events) == 2
        assert msg_id1 in events
        assert msg_id2 in events

        # Check reverse mapping
        concepts1 = graph.concepts_for_event(msg_id1)
        assert "topic.system_maturity" in concepts1

        concepts2 = graph.concepts_for_event(msg_id2)
        assert "topic.system_maturity" in concepts2

    def test_multiple_concepts_per_event(self):
        log = EventLog()

        msg_id = log.append(kind="user_message", content="Test", meta={})

        # Define concepts
        for token in ["topic.A", "topic.B", "topic.C"]:
            content, meta = create_concept_define_payload(
                token=token, concept_kind="topic", definition=f"Topic {token}"
            )
            log.append(kind="concept_define", content=content, meta=meta)

        # Bind multiple concepts to one event
        content, meta = create_concept_bind_event_payload(
            event_id=msg_id,
            tokens=["topic.A", "topic.B", "topic.C"],
            relation="mention",
        )
        log.append(kind="concept_bind_event", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        concepts = graph.concepts_for_event(msg_id)
        assert len(concepts) == 3
        assert set(concepts) == {"topic.A", "topic.B", "topic.C"}


class TestConceptRelationships:
    def test_concept_relate(self):
        log = EventLog()

        # Define concepts
        for token, kind in [
            ("topic.system_maturity", "topic"),
            ("policy.stability_v2", "policy"),
        ]:
            content, meta = create_concept_define_payload(
                token=token, concept_kind=kind, definition=f"Definition of {token}"
            )
            log.append(kind="concept_define", content=content, meta=meta)

        # Create relationship
        content, meta = create_concept_relate_payload(
            from_token="topic.system_maturity",
            to_token="policy.stability_v2",
            relation="influences",
        )
        log.append(kind="concept_relate", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check neighbors
        neighbors = graph.neighbors("topic.system_maturity")
        assert "policy.stability_v2" in neighbors

        neighbors_reverse = graph.neighbors("policy.stability_v2")
        assert "topic.system_maturity" in neighbors_reverse

        # Check directed neighbors
        outgoing = graph.outgoing_neighbors("topic.system_maturity")
        assert "policy.stability_v2" in outgoing

        incoming = graph.incoming_neighbors("policy.stability_v2")
        assert "topic.system_maturity" in incoming

    def test_concept_relate_with_relation_filter(self):
        log = EventLog()

        # Define concepts
        for token in ["A", "B", "C"]:
            content, meta = create_concept_define_payload(
                token=f"concept.{token}",
                concept_kind="test",
                definition=f"Concept {token}",
            )
            log.append(kind="concept_define", content=content, meta=meta)

        # Create different types of relationships
        relations = [
            ("concept.A", "concept.B", "influences"),
            ("concept.A", "concept.C", "depends_on"),
        ]

        for from_tok, to_tok, relation in relations:
            content, meta = create_concept_relate_payload(
                from_token=from_tok, to_token=to_tok, relation=relation
            )
            log.append(kind="concept_relate", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Filter by relation
        influences_neighbors = graph.neighbors("concept.A", relation="influences")
        assert influences_neighbors == ["concept.B"]

        depends_neighbors = graph.neighbors("concept.A", relation="depends_on")
        assert depends_neighbors == ["concept.C"]

        all_neighbors = graph.neighbors("concept.A")
        assert set(all_neighbors) == {"concept.B", "concept.C"}


class TestConceptGraphRebuildAndSync:
    def test_rebuild_equals_sync(self):
        log = EventLog()

        # Add various concept events
        content1, meta1 = create_concept_define_payload(
            token="identity.Echo",
            concept_kind="identity",
            definition="Primary identity",
        )
        log.append(kind="concept_define", content=content1, meta=meta1)

        content2, meta2 = create_concept_alias_payload(
            from_token="identity.PMM", to_token="identity.Echo"
        )
        log.append(kind="concept_alias", content=content2, meta=meta2)

        msg_id = log.append(kind="user_message", content="Test", meta={})

        content3, meta3 = create_concept_bind_event_payload(
            event_id=msg_id, tokens=["identity.Echo"], relation="mention"
        )
        log.append(kind="concept_bind_event", content=content3, meta=meta3)

        # Rebuild from scratch
        graph1 = ConceptGraph(log)
        graph1.rebuild()

        # Build incrementally via sync
        graph2 = ConceptGraph(log)
        graph2.rebuild([])  # Start empty
        for event in log.read_all():
            graph2.sync(event)

        # Should be identical
        assert len(graph1.concepts) == len(graph2.concepts)
        assert len(graph1.aliases) == len(graph2.aliases)
        assert len(graph1.concept_edges) == len(graph2.concept_edges)
        assert len(graph1.concept_event_bindings) == len(graph2.concept_event_bindings)
        assert graph1.stats() == graph2.stats()

    def test_sync_idempotency(self):
        log = EventLog()

        content, meta = create_concept_define_payload(
            token="test.token", concept_kind="test", definition="Test"
        )
        event_id = log.append(kind="concept_define", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        initial_stats = graph.stats()

        # Sync same event again (should be idempotent)
        event = log.get(event_id)
        graph.sync(event)

        # Stats should be unchanged
        assert graph.stats() == initial_stats


class TestConceptGraphStats:
    def test_stats_comprehensive(self):
        log = EventLog()

        # Add concepts of different kinds
        concepts = [
            ("identity.Echo", "identity"),
            ("identity.User", "identity"),
            ("policy.stability_v1", "policy"),
            ("policy.stability_v2", "policy"),
            ("topic.maturity", "topic"),
        ]

        for token, kind in concepts:
            content, meta = create_concept_define_payload(
                token=token, concept_kind=kind, definition=f"Definition of {token}"
            )
            log.append(kind="concept_define", content=content, meta=meta)

        # Add aliases
        content, meta = create_concept_alias_payload(
            from_token="identity.PMM", to_token="identity.Echo"
        )
        log.append(kind="concept_alias", content=content, meta=meta)

        # Add bindings
        msg_id = log.append(kind="user_message", content="Test", meta={})
        content, meta = create_concept_bind_event_payload(
            event_id=msg_id, tokens=["identity.Echo", "topic.maturity"]
        )
        log.append(kind="concept_bind_event", content=content, meta=meta)

        # Add relationships
        content, meta = create_concept_relate_payload(
            from_token="topic.maturity",
            to_token="policy.stability_v2",
            relation="influences",
        )
        log.append(kind="concept_relate", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        stats = graph.stats()

        assert stats["total_concepts"] == 5
        assert stats["total_aliases"] == 1
        assert stats["total_edges"] == 1
        assert stats["total_bindings"] == 2
        assert stats["concepts_by_kind"]["identity"] == 2
        assert stats["concepts_by_kind"]["policy"] == 2
        assert stats["concepts_by_kind"]["topic"] == 1
        assert stats["edges_by_relation"]["influences"] == 1


class TestConceptGraphQueries:
    def test_all_tokens(self):
        log = EventLog()

        tokens = ["identity.Echo", "policy.stability_v2", "topic.maturity"]
        for token in tokens:
            content, meta = create_concept_define_payload(
                token=token, concept_kind="test", definition="Test"
            )
            log.append(kind="concept_define", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        all_tokens = graph.all_tokens()
        assert all_tokens == sorted(tokens)

    def test_tokens_by_kind(self):
        log = EventLog()

        concepts = [
            ("identity.Echo", "identity"),
            ("identity.User", "identity"),
            ("policy.stability_v2", "policy"),
            ("topic.maturity", "topic"),
        ]

        for token, kind in concepts:
            content, meta = create_concept_define_payload(
                token=token, concept_kind=kind, definition="Test"
            )
            log.append(kind="concept_define", content=content, meta=meta)

        graph = ConceptGraph(log)
        graph.rebuild()

        identity_tokens = graph.tokens_by_kind("identity")
        assert identity_tokens == ["identity.Echo", "identity.User"]

        policy_tokens = graph.tokens_by_kind("policy")
        assert policy_tokens == ["policy.stability_v2"]

        topic_tokens = graph.tokens_by_kind("topic")
        assert topic_tokens == ["topic.maturity"]

    def test_get_history(self):
        log = EventLog()

        # Define v1
        content1, meta1 = create_concept_define_payload(
            token="policy.stability",
            concept_kind="policy",
            definition="Stability policy v1",
            version=1,
        )
        log.append(kind="concept_define", content=content1, meta=meta1)

        # Define v2 (supersedes v1)
        content2, meta2 = create_concept_define_payload(
            token="policy.stability",
            concept_kind="policy",
            definition="Stability policy v2",
            version=2,
            supersedes=meta1["concept_id"],
        )
        log.append(kind="concept_define", content=content2, meta=meta2)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Current definition should be v2
        current = graph.get_definition("policy.stability")
        assert current is not None
        assert current.version == 2
        assert current.definition == "Stability policy v2"

        # History should have both versions
        history = graph.get_history("policy.stability")
        assert len(history) == 2
        assert history[0].version == 1
        assert history[1].version == 2
        assert history[1].supersedes == meta1["concept_id"]
