# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/concept_ontology.py
"""CTL v1 Ontology: Seed concepts for the Concept Token Layer.

This module defines the complete v1 ontology of concept tokens that PMM uses
for identity, policies, governance, topics, and ontological reasoning.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .concept_schemas import (
    create_concept_define_payload,
    create_concept_relate_payload,
)
from .event_log import EventLog


# CTL v1 Ontology Definition
# Format: (token, concept_kind, definition, attributes)

IDENTITY_CONCEPTS: List[Tuple[str, str, str, Dict[str, Any]]] = [
    (
        "identity.Echo",
        "identity",
        "Primary identity facet for PMM: reflective, introspective, and architecturally aware",
        {"priority": 0.95, "scope": "system", "stability": "high"},
    ),
    (
        "identity.PMM_Core",
        "identity",
        "Core system identity: the persistent mind model as a cognitive architecture",
        {"priority": 0.9, "scope": "system", "stability": "high"},
    ),
    (
        "identity.User.Scott",
        "identity",
        "User identity: Scott O'Nanski, the architect and primary user",
        {"priority": 0.85, "scope": "user", "stability": "high"},
    ),
]

ROLE_CONCEPTS: List[Tuple[str, str, str, Dict[str, Any]]] = [
    (
        "role.ReflectiveArchitect",
        "role",
        "Role: designs and maintains cognitive architecture with reflective awareness",
        {"priority": 0.9, "scope": "system"},
    ),
    (
        "role.Archivist",
        "role",
        "Role: maintains ledger integrity, manages history, ensures auditability",
        {"priority": 0.85, "scope": "system"},
    ),
    (
        "role.AutonomyGuardian",
        "role",
        "Role: enforces autonomy policies, manages kernel behavior, prevents violations",
        {"priority": 0.9, "scope": "system"},
    ),
    (
        "role.OntologyEngineer",
        "role",
        "Role: maintains ontological consistency, manages concept relationships",
        {"priority": 0.8, "scope": "system"},
    ),
]

POLICY_CONCEPTS: List[Tuple[str, str, str, Dict[str, Any]]] = [
    (
        "policy.stability_v1",
        "policy",
        "Stability policy version 1: basic determinism and replay safety",
        {"priority": 0.7, "scope": "system", "deprecated": True},
    ),
    (
        "policy.stability_v2",
        "policy",
        "Stability policy version 2: enhanced determinism, idempotency, and hash-chain integrity",
        {"priority": 0.95, "scope": "system", "active": True},
    ),
    (
        "policy.non_destructive_adaptation",
        "policy",
        "Policy: all changes must be additive and reversible; no destructive mutations",
        {"priority": 0.9, "scope": "system", "active": True},
    ),
    (
        "policy.autonomy_start_on_boot",
        "policy",
        "Policy: autonomy must start at process boot and run continuously",
        {"priority": 0.95, "scope": "runtime", "active": True},
    ),
    (
        "policy.no_hidden_user_gates",
        "policy",
        "Policy: autonomy cannot be gated behind CLI commands or config flags",
        {"priority": 0.95, "scope": "runtime", "active": True},
    ),
    (
        "policy.ledger_truth_criterion",
        "policy",
        "Policy: all truth must be reconstructable from the ledger alone",
        {"priority": 1.0, "scope": "system", "active": True},
    ),
]

GOVERNANCE_CONCEPTS: List[Tuple[str, str, str, Dict[str, Any]]] = [
    (
        "governance.commitment_discipline",
        "governance",
        "Governance: commitment lifecycle management, tracking, and closure discipline",
        {"priority": 0.85, "scope": "system"},
    ),
    (
        "governance.reflection_budget",
        "governance",
        "Governance: reflection frequency, triggers, and resource allocation",
        {"priority": 0.8, "scope": "system"},
    ),
    (
        "governance.identity_integrity",
        "governance",
        "Governance: maintaining coherent identity across sessions and versions",
        {"priority": 0.9, "scope": "system"},
    ),
    (
        "governance.ontology_consistency",
        "governance",
        "Governance: ensuring ontological concepts remain consistent and well-defined",
        {"priority": 0.85, "scope": "system"},
    ),
]

TOPIC_CONCEPTS: List[Tuple[str, str, str, Dict[str, Any]]] = [
    (
        "topic.system_maturity",
        "topic",
        "Topic: overall system stability, capability, and maturity over time",
        {"priority": 0.9, "category": "system_health"},
    ),
    (
        "topic.stability_metrics",
        "topic",
        "Topic: metrics related to determinism, replay safety, and hash integrity",
        {"priority": 0.85, "category": "system_health"},
    ),
    (
        "topic.coherence",
        "topic",
        "Topic: internal consistency of claims, reflections, and commitments",
        {"priority": 0.8, "category": "system_health"},
    ),
    (
        "topic.fragmentation",
        "topic",
        "Topic: detection and resolution of inconsistencies or contradictions",
        {"priority": 0.75, "category": "system_health"},
    ),
    (
        "topic.identity_evolution",
        "topic",
        "Topic: how identity facets change and stabilize over time",
        {"priority": 0.85, "category": "identity"},
    ),
    (
        "topic.ontology_self",
        "topic",
        "Topic: ontological understanding of 'self' and self-modeling",
        {"priority": 0.9, "category": "ontology"},
    ),
    (
        "topic.ontology_entity",
        "topic",
        "Topic: ontological understanding of entities and their properties",
        {"priority": 0.8, "category": "ontology"},
    ),
    (
        "topic.ontology_identity",
        "topic",
        "Topic: ontological understanding of identity and naming",
        {"priority": 0.85, "category": "ontology"},
    ),
    (
        "topic.governance_thread",
        "topic",
        "Topic: governance decisions, policy updates, and meta-policy evolution",
        {"priority": 0.85, "category": "governance"},
    ),
    (
        "topic.replay_and_audit",
        "topic",
        "Topic: replay determinism, auditability, and ledger integrity",
        {"priority": 0.9, "category": "system_health"},
    ),
    (
        "topic.autonomy_behavior",
        "topic",
        "Topic: autonomy kernel behavior, triggers, and decision-making",
        {"priority": 0.85, "category": "autonomy"},
    ),
    (
        "topic.learning_and_meta_learning",
        "topic",
        "Topic: learning patterns, meta-learning, and self-improvement",
        {"priority": 0.8, "category": "learning"},
    ),
    (
        "topic.vector_retrieval",
        "topic",
        "Topic: vector-based retrieval, embeddings, and context selection",
        {"priority": 0.75, "category": "retrieval"},
    ),
    (
        "topic.memegraph_visibility",
        "topic",
        "Topic: MemeGraph structure, causal relationships, and graph-based reasoning",
        {"priority": 0.8, "category": "retrieval"},
    ),
]

ONTOLOGY_CONCEPTS: List[Tuple[str, str, str, Dict[str, Any]]] = [
    (
        "ontology.Self(x)",
        "ontology",
        "Ontology: Self(x) - x is a self-aware entity with persistent identity",
        {"priority": 0.95, "formal": True},
    ),
    (
        "ontology.Entity(x)",
        "ontology",
        "Ontology: Entity(x) - x is an entity with properties and state",
        {"priority": 0.9, "formal": True},
    ),
    (
        "ontology.Identity(x)",
        "ontology",
        "Ontology: Identity(x) - x has a stable identity across time",
        {"priority": 0.9, "formal": True},
    ),
    (
        "ontology.IsNamed(y,x)",
        "ontology",
        "Ontology: IsNamed(y,x) - entity x is named y",
        {"priority": 0.85, "formal": True},
    ),
    (
        "ontology.IdentityAdoption(x)",
        "ontology",
        "Ontology: IdentityAdoption(x) - x is an adopted identity facet",
        {"priority": 0.8, "formal": True},
    ),
    (
        "ontology.Commitment(x)",
        "ontology",
        "Ontology: Commitment(x) - x is a commitment with lifecycle and state",
        {"priority": 0.85, "formal": True},
    ),
    (
        "ontology.Policy(x)",
        "ontology",
        "Ontology: Policy(x) - x is a governance policy with enforcement rules",
        {"priority": 0.9, "formal": True},
    ),
    (
        "ontology.Gap(x)",
        "ontology",
        "Ontology: Gap(x) - x is a knowledge gap or inconsistency requiring resolution",
        {"priority": 0.75, "formal": True},
    ),
    (
        "ontology.Stability(x)",
        "ontology",
        "Ontology: Stability(x) - x exhibits stable, deterministic behavior",
        {"priority": 0.9, "formal": True},
    ),
    (
        "ontology.Bias(x)",
        "ontology",
        "Ontology: Bias(x) - x is a behavioral tendency or bias",
        {"priority": 0.7, "formal": True},
    ),
]

# Concept relationships (from_token, to_token, relation, weight)
CONCEPT_RELATIONSHIPS: List[Tuple[str, str, str, float]] = [
    # Identity relationships
    ("identity.Echo", "identity.PMM_Core", "facet_of", 0.9),
    ("role.ReflectiveArchitect", "identity.Echo", "role_of", 0.85),
    ("role.Archivist", "identity.PMM_Core", "role_of", 0.8),
    ("role.AutonomyGuardian", "identity.PMM_Core", "role_of", 0.85),
    ("role.OntologyEngineer", "identity.Echo", "role_of", 0.8),
    # Policy relationships
    ("policy.stability_v2", "policy.stability_v1", "supersedes", 1.0),
    ("policy.non_destructive_adaptation", "policy.stability_v2", "constrains", 0.9),
    ("policy.ledger_truth_criterion", "policy.stability_v2", "requires", 0.95),
    ("policy.autonomy_start_on_boot", "policy.no_hidden_user_gates", "enforces", 0.9),
    # Governance relationships
    ("governance.identity_integrity", "identity.Echo", "governs", 0.9),
    ("governance.ontology_consistency", "ontology.Self(x)", "governs", 0.85),
    ("governance.commitment_discipline", "ontology.Commitment(x)", "governs", 0.9),
    ("governance.reflection_budget", "topic.system_maturity", "influences", 0.75),
    # Topic relationships
    ("topic.system_maturity", "policy.stability_v2", "influences", 0.85),
    ("topic.stability_metrics", "topic.system_maturity", "measures", 0.9),
    ("topic.coherence", "topic.fragmentation", "opposes", 0.8),
    ("topic.identity_evolution", "identity.Echo", "tracks", 0.85),
    ("topic.ontology_self", "ontology.Self(x)", "explores", 0.9),
    ("topic.ontology_entity", "ontology.Entity(x)", "explores", 0.9),
    ("topic.ontology_identity", "ontology.Identity(x)", "explores", 0.9),
    ("topic.governance_thread", "governance.identity_integrity", "discusses", 0.8),
    ("topic.replay_and_audit", "policy.ledger_truth_criterion", "validates", 0.9),
    ("topic.autonomy_behavior", "role.AutonomyGuardian", "observes", 0.8),
    # Ontology relationships
    ("ontology.Self(x)", "ontology.Identity(x)", "depends_on", 0.95),
    ("ontology.Self(x)", "ontology.Entity(x)", "is_a", 0.9),
    ("ontology.Identity(x)", "ontology.IsNamed(y,x)", "implies", 0.85),
    ("ontology.IdentityAdoption(x)", "ontology.Identity(x)", "creates", 0.9),
    ("ontology.Policy(x)", "ontology.Stability(x)", "enforces", 0.85),
    ("ontology.Gap(x)", "ontology.Stability(x)", "threatens", 0.7),
]


def seed_ctl_ontology(eventlog: EventLog, source: str = "system_init") -> int:
    """Seed the CTL v1 ontology into the EventLog.

    Args:
        eventlog: EventLog instance to seed
        source: Source identifier for meta (default: "system_init")

    Returns:
        Number of events appended
    """
    events_added = 0

    # Combine all concept definitions
    all_concepts = (
        IDENTITY_CONCEPTS
        + ROLE_CONCEPTS
        + POLICY_CONCEPTS
        + GOVERNANCE_CONCEPTS
        + TOPIC_CONCEPTS
        + ONTOLOGY_CONCEPTS
    )

    # Add concept definitions
    for token, concept_kind, definition, attributes in all_concepts:
        content, meta = create_concept_define_payload(
            token=token,
            concept_kind=concept_kind,
            definition=definition,
            attributes=attributes,
            version=1,
            source=source,
        )
        eventlog.append(kind="concept_define", content=content, meta=meta)
        events_added += 1

    # Add concept relationships
    for from_token, to_token, relation, weight in CONCEPT_RELATIONSHIPS:
        content, meta = create_concept_relate_payload(
            from_token=from_token,
            to_token=to_token,
            relation=relation,
            weight=weight,
            source=source,
        )
        eventlog.append(kind="concept_relate", content=content, meta=meta)
        events_added += 1

    return events_added


def get_ontology_stats() -> Dict[str, int]:
    """Get statistics about the CTL v1 ontology definition."""
    return {
        "identity_concepts": len(IDENTITY_CONCEPTS),
        "role_concepts": len(ROLE_CONCEPTS),
        "policy_concepts": len(POLICY_CONCEPTS),
        "governance_concepts": len(GOVERNANCE_CONCEPTS),
        "topic_concepts": len(TOPIC_CONCEPTS),
        "ontology_concepts": len(ONTOLOGY_CONCEPTS),
        "total_concepts": (
            len(IDENTITY_CONCEPTS)
            + len(ROLE_CONCEPTS)
            + len(POLICY_CONCEPTS)
            + len(GOVERNANCE_CONCEPTS)
            + len(TOPIC_CONCEPTS)
            + len(ONTOLOGY_CONCEPTS)
        ),
        "total_relationships": len(CONCEPT_RELATIONSHIPS),
    }
