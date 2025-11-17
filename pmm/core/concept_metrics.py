# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Concept-level metrics and state tracking for CTL integration with RSM."""

from __future__ import annotations

from typing import Dict, List
from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph


def compute_concept_metrics(eventlog: EventLog) -> Dict[str, any]:
    """Compute concept-level metrics for RSM integration.

    Returns:
        Dictionary with:
        - concepts_used: Dict[token, count] - concept usage counts
        - concept_gaps: List[token] - concepts with low evidence
        - concept_conflicts: List[token] - concepts with conflicting relations
        - hot_concepts: List[token] - recently active concepts
    """
    cg = ConceptGraph(eventlog)
    cg.rebuild(eventlog.read_all())

    # Compute usage counts
    concepts_used: Dict[str, int] = {}
    for token in cg.concepts.keys():
        events = cg.events_for_concept(token)
        concepts_used[token] = len(events)

    # Identify gaps (concepts with < 2 bindings)
    concept_gaps: List[str] = []
    for token, count in concepts_used.items():
        if count < 2:
            concept_gaps.append(token)

    # Identify conflicts (concepts with multiple conflicting relations)
    # For now, just check if a concept has both "supports" and "conflicts_with" relations
    concept_conflicts: List[str] = []
    for token in cg.concepts.keys():
        # Check for conflicting relation patterns
        supports = cg.neighbors(token, relation="supports")
        conflicts = cg.neighbors(token, relation="conflicts_with")
        if supports and conflicts:
            concept_conflicts.append(token)

    # Hot concepts (top 5 by recent activity)
    # Sort by binding count descending
    hot_concepts: List[str] = sorted(
        concepts_used.keys(), key=lambda t: (-concepts_used[t], t)
    )[:5]

    return {
        "concepts_used": concepts_used,
        "concept_gaps": sorted(concept_gaps),
        "concept_conflicts": sorted(concept_conflicts),
        "hot_concepts": hot_concepts,
    }


def get_governance_concepts(eventlog: EventLog) -> List[str]:
    """Get list of governance/policy concept tokens.

    Returns:
        Sorted list of governance-related concept tokens
    """
    cg = ConceptGraph(eventlog)
    cg.rebuild(eventlog.read_all())

    governance_tokens: List[str] = []
    for token in cg.concepts.keys():
        # Governance concepts start with "policy." or "governance."
        if token.startswith("policy.") or token.startswith("governance."):
            governance_tokens.append(token)

    return sorted(governance_tokens)


def check_concept_health(eventlog: EventLog) -> Dict[str, any]:
    """Check health of concept layer for autonomy decisions.

    Returns:
        Dictionary with:
        - total_concepts: int
        - total_bindings: int
        - avg_bindings_per_concept: float
        - governance_concept_count: int
        - gap_count: int
        - conflict_count: int
        - health_score: float (0.0-1.0)
    """
    metrics = compute_concept_metrics(eventlog)
    governance = get_governance_concepts(eventlog)

    total_concepts = len(metrics["concepts_used"])
    total_bindings = sum(metrics["concepts_used"].values())
    avg_bindings = total_bindings / total_concepts if total_concepts > 0 else 0.0

    gap_count = len(metrics["concept_gaps"])
    conflict_count = len(metrics["concept_conflicts"])
    governance_count = len(governance)

    # Simple health score: penalize gaps and conflicts
    if total_concepts == 0:
        health_score = 0.0
    else:
        gap_penalty = gap_count / total_concepts
        conflict_penalty = conflict_count / total_concepts
        health_score = max(0.0, 1.0 - gap_penalty - conflict_penalty)

    return {
        "total_concepts": total_concepts,
        "total_bindings": total_bindings,
        "avg_bindings_per_concept": round(avg_bindings, 2),
        "governance_concept_count": governance_count,
        "gap_count": gap_count,
        "conflict_count": conflict_count,
        "health_score": round(health_score, 2),
    }
