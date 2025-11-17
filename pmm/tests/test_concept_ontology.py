# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_concept_ontology.py
"""Tests for CTL v1 ontology seeding."""


from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.core.concept_ontology import seed_ctl_ontology, get_ontology_stats


class TestOntologySeeding:
    def test_seed_ctl_ontology(self):
        log = EventLog()

        events_added = seed_ctl_ontology(log)

        # Should have added concepts + relationships
        stats = get_ontology_stats()
        expected_events = stats["total_concepts"] + stats["total_relationships"]
        assert events_added == expected_events

        # Check events were actually added
        all_events = log.read_all()
        concept_defines = [e for e in all_events if e["kind"] == "concept_define"]
        concept_relates = [e for e in all_events if e["kind"] == "concept_relate"]

        assert len(concept_defines) == stats["total_concepts"]
        assert len(concept_relates) == stats["total_relationships"]

    def test_ontology_rebuilds_in_concept_graph(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        stats = get_ontology_stats()

        # All concepts should be in graph
        assert graph.stats()["total_concepts"] == stats["total_concepts"]
        assert graph.stats()["total_edges"] == stats["total_relationships"]

    def test_identity_concepts_present(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check key identity concepts
        assert graph.get_definition("identity.Echo") is not None
        assert graph.get_definition("identity.PMM_Core") is not None
        assert graph.get_definition("identity.User.Scott") is not None

        identity_tokens = graph.tokens_by_kind("identity")
        assert len(identity_tokens) == 3

    def test_role_concepts_present(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check key role concepts
        assert graph.get_definition("role.ReflectiveArchitect") is not None
        assert graph.get_definition("role.Archivist") is not None
        assert graph.get_definition("role.AutonomyGuardian") is not None
        assert graph.get_definition("role.OntologyEngineer") is not None

        role_tokens = graph.tokens_by_kind("role")
        assert len(role_tokens) == 4

    def test_policy_concepts_present(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check key policy concepts
        assert graph.get_definition("policy.stability_v2") is not None
        assert graph.get_definition("policy.non_destructive_adaptation") is not None
        assert graph.get_definition("policy.ledger_truth_criterion") is not None

        policy_tokens = graph.tokens_by_kind("policy")
        assert len(policy_tokens) == 6

    def test_governance_concepts_present(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check key governance concepts
        assert graph.get_definition("governance.commitment_discipline") is not None
        assert graph.get_definition("governance.identity_integrity") is not None
        assert graph.get_definition("governance.ontology_consistency") is not None

        governance_tokens = graph.tokens_by_kind("governance")
        assert len(governance_tokens) == 4

    def test_topic_concepts_present(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check key topic concepts
        assert graph.get_definition("topic.system_maturity") is not None
        assert graph.get_definition("topic.stability_metrics") is not None
        assert graph.get_definition("topic.coherence") is not None
        assert graph.get_definition("topic.ontology_self") is not None

        topic_tokens = graph.tokens_by_kind("topic")
        assert len(topic_tokens) == 14

    def test_ontology_concepts_present(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check key ontology concepts
        assert graph.get_definition("ontology.Self(x)") is not None
        assert graph.get_definition("ontology.Entity(x)") is not None
        assert graph.get_definition("ontology.Identity(x)") is not None
        assert graph.get_definition("ontology.Commitment(x)") is not None

        ontology_tokens = graph.tokens_by_kind("ontology")
        assert len(ontology_tokens) == 10

    def test_concept_relationships_established(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Test some key relationships

        # identity.Echo should be facet_of identity.PMM_Core
        neighbors = graph.outgoing_neighbors("identity.Echo", relation="facet_of")
        assert "identity.PMM_Core" in neighbors

        # policy.stability_v2 should supersede policy.stability_v1
        neighbors = graph.outgoing_neighbors(
            "policy.stability_v2", relation="supersedes"
        )
        assert "policy.stability_v1" in neighbors

        # ontology.Self(x) should depend_on ontology.Identity(x)
        neighbors = graph.outgoing_neighbors("ontology.Self(x)", relation="depends_on")
        assert "ontology.Identity(x)" in neighbors

        # topic.system_maturity should influence policy.stability_v2
        neighbors = graph.outgoing_neighbors(
            "topic.system_maturity", relation="influences"
        )
        assert "policy.stability_v2" in neighbors

    def test_ontology_stats(self):
        stats = get_ontology_stats()

        # Verify expected counts
        assert stats["identity_concepts"] == 3
        assert stats["role_concepts"] == 4
        assert stats["policy_concepts"] == 6
        assert stats["governance_concepts"] == 4
        assert stats["topic_concepts"] == 14
        assert stats["ontology_concepts"] == 10
        assert stats["total_concepts"] == 41
        assert stats["total_relationships"] > 0

    def test_ontology_deterministic(self):
        # Seeding twice should produce identical results
        log1 = EventLog()
        events1 = seed_ctl_ontology(log1)

        log2 = EventLog()
        events2 = seed_ctl_ontology(log2)

        assert events1 == events2

        # Hash sequences should be identical
        hashes1 = log1.hash_sequence()
        hashes2 = log2.hash_sequence()
        assert hashes1 == hashes2

    def test_concept_attributes(self):
        log = EventLog()
        seed_ctl_ontology(log)

        graph = ConceptGraph(log)
        graph.rebuild()

        # Check that attributes are preserved
        echo = graph.get_definition("identity.Echo")
        assert echo is not None
        assert echo.attributes.get("priority") == 0.95
        assert echo.attributes.get("scope") == "system"
        assert echo.attributes.get("stability") == "high"

        stability_v2 = graph.get_definition("policy.stability_v2")
        assert stability_v2 is not None
        assert stability_v2.attributes.get("active") is True
        assert stability_v2.attributes.get("priority") == 0.95
