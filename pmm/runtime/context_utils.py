# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Shared helpers for rendering runtime context blocks."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from pmm.core.commitment_manager import CommitmentManager
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph


def render_identity_claims(eventlog: EventLog) -> str:
    """Render identity claims (e.g., name) from ledger claim events."""
    events = eventlog.read_all()
    identity_facts: Dict[str, str] = {}

    for event in events:
        if event.get("kind") != "claim":
            continue
        meta = event.get("meta") or {}
        claim_type = meta.get("claim_type")

        if claim_type == "name_change":
            try:
                content = event.get("content", "")
                if "=" in content:
                    _, json_part = content.split("=", 1)
                    data = json.loads(json_part)
                    if "new_name" in data:
                        identity_facts["name"] = data["new_name"]
            except (ValueError, json.JSONDecodeError):
                continue

    if not identity_facts:
        return ""

    parts = [f"{key}: {value}" for key, value in sorted(identity_facts.items())]
    return "Identity: " + ", ".join(parts)


def render_rsm(snapshot: Dict[str, Any]) -> str:
    """Render recursive self-model information from a mirror snapshot."""
    if not snapshot:
        return ""
    tendencies = snapshot.get("behavioral_tendencies") or {}
    gaps = snapshot.get("knowledge_gaps") or []
    meta_patterns = snapshot.get("interaction_meta_patterns") or []

    nonzero_tendencies = {k: v for k, v in tendencies.items() if v}
    if (
        nonzero_tendencies.keys() == {"uniqueness_emphasis"}
        and not gaps
        and not meta_patterns
    ):
        return ""
    if not (tendencies or gaps or meta_patterns):
        return ""

    tendency_parts = [f"{key} ({tendencies[key]})" for key in sorted(tendencies.keys())]
    gaps_part = ", ".join(gaps)
    tendencies_text = ", ".join(tendency_parts) if tendency_parts else "none"
    gaps_text = gaps_part if gaps_part else "none"
    lines = [
        "Recursive Self-Model:",
        f"- Tendencies: {tendencies_text}",
        f"- Gaps: {gaps_text}",
    ]
    return "\n".join(lines)


def render_internal_goals(eventlog: EventLog) -> str:
    """Render internal goals from open commitments."""
    manager = CommitmentManager(eventlog)
    open_internal = manager.get_open_commitments(origin="autonomy_kernel")
    parts: List[str] = []
    for event in open_internal:
        meta = event.get("meta") or {}
        cid = meta.get("cid")
        goal = meta.get("goal") or "unknown"
        if not cid:
            continue
        parts.append(f"{cid} ({goal})")
    if not parts:
        return ""
    return f"Internal Goals: {', '.join(parts)}"


def render_graph_context(eventlog: EventLog) -> str:
    """Render memegraph structural context for model introspection."""
    mg = MemeGraph(eventlog)
    mg.rebuild(eventlog.read_all())
    stats = mg.graph_stats()

    if stats["nodes"] < 5:
        return ""

    lines: List[str] = []

    if stats["nodes"] <= 8:
        lines.append(f"Graph: {stats['nodes']} nodes, {stats['edges']} edges")
    else:
        lines.append(
            "Graph Context:\n- Connections: "
            f"{stats['edges']} edges, {stats['nodes']} nodes"
        )

    manager = CommitmentManager(eventlog)
    open_comms = manager.get_open_commitments()
    thread_parts: List[str] = []

    for comm in open_comms[:3]:
        meta = comm.get("meta") or {}
        cid = meta.get("cid")
        if not cid:
            continue
        thread = mg.thread_for_cid(cid)
        if thread:
            thread_parts.append(f"{cid}:{len(thread)}")

    if thread_parts:
        if len(lines) == 1 and not lines[0].startswith("Graph Context"):
            lines.append(f"Threads: {', '.join(thread_parts)}")
        else:
            lines.append(f"- Thread depths: {', '.join(thread_parts)}")

    return "\n".join(lines)


def render_concept_context(eventlog: EventLog, *, limit: int = 5) -> str:
    """Render concept context showing hot/active concepts.

    Displays:
    - Recently bound concepts (high activity)
    - Governance/policy concepts
    - Concepts with many bindings

    Args:
        eventlog: EventLog instance
        limit: Maximum number of concepts to display

    Returns:
        Formatted concept context string, or empty if no concepts
    """
    from pmm.core.concept_graph import ConceptGraph

    cg = ConceptGraph(eventlog)
    cg.rebuild(eventlog.read_all())

    stats = cg.stats()
    if stats["total_concepts"] == 0:
        return ""

    # Collect concepts with binding counts
    concept_activity: List[tuple[str, int]] = []
    for token in cg.concepts.keys():
        events = cg.events_for_concept(token)
        if events:
            concept_activity.append((token, len(events)))

    if not concept_activity:
        return ""

    # Sort by activity (descending) and take top N
    concept_activity.sort(key=lambda x: (-x[1], x[0]))
    top_concepts = concept_activity[:limit]

    # Build context lines
    lines: List[str] = ["Concept Context:"]

    for token, count in top_concepts:
        defn = cg.get_definition(token)
        if defn:
            # Show token, definition snippet, and binding count
            defn_snippet = (
                defn.definition[:40] + "..."
                if len(defn.definition) > 40
                else defn.definition
            )
            lines.append(f"- {token}: {defn_snippet} ({count} refs)")
        else:
            lines.append(f"- {token}: ({count} refs)")

    return "\n".join(lines)
