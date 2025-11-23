# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Context renderer for PMM.

Renders a 4-section context based on deterministic retrieval results:
1. CTL Story
2. Threads / Projects
3. State & Self-Model
4. Raw Evidence
"""

from __future__ import annotations

from typing import List
from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.core.meme_graph import MemeGraph
from pmm.core.mirror import Mirror
from pmm.retrieval.pipeline import RetrievalResult
from pmm.runtime.context_utils import (
    render_identity_claims,
    render_rsm,
    render_graph_context,
)


def render_context(
    *,
    result: RetrievalResult,
    eventlog: EventLog,
    concept_graph: ConceptGraph,
    meme_graph: MemeGraph,
    mirror: Mirror,
) -> str:
    """Render the full context string."""

    sections: List[str] = []

    # 1. High-Level CTL Story
    ctl_section = _render_ctl_story(result, concept_graph)
    if ctl_section:
        sections.append(ctl_section)

    # 2. Threads / Projects
    threads_section = _render_threads(result, meme_graph, concept_graph, eventlog)
    if threads_section:
        sections.append(threads_section)

    # 2b. Graph structure (conditional; only when graph has structure)
    graph_section = render_graph_context(eventlog, meme_graph=meme_graph)
    if graph_section:
        sections.append(graph_section)

    # 3. State & Self-Model
    state_section = _render_state_model(eventlog, mirror, result)
    if state_section:
        sections.append(state_section)

    # 4. Raw Evidence
    evidence_section = _render_evidence(result.event_ids, eventlog)
    if evidence_section:
        sections.append(evidence_section)

    return "\n\n".join(sections)


def _render_ctl_story(result: RetrievalResult, cg: ConceptGraph) -> str:
    """Render active concepts and their relations."""
    if not result.active_concepts:
        return ""

    lines = ["## Concepts"]

    # Sort concepts by some deterministic metric (e.g. name) since they are seeds
    for token in sorted(result.active_concepts):
        defn = cg.get_definition(token)
        desc = ""
        if defn:
            desc = f": {defn.definition}"
            if len(desc) > 60:
                desc = desc[:57] + "..."
        lines.append(f"- {token}{desc}")

        # Add relations?
        # "Relations between them (e.g. policy.*, governance.*)"
        # Let's query neighbors restricted to active concepts?
        # Or just list immediate neighbors in the graph that are also in active_concepts?
        neighbors = cg.neighbors(token)
        active_neighbors = [
            n for n in neighbors if n in result.active_concepts and n > token
        ]  # n > token dedupes undirected
        if active_neighbors:
            lines.append(f"  - Linked to: {', '.join(active_neighbors)}")

    return "\n".join(lines)


def _render_threads(
    result: RetrievalResult, mg: MemeGraph, cg: ConceptGraph, eventlog: EventLog
) -> str:
    """Render summaries of relevant threads."""
    if not result.relevant_cids:
        return ""

    lines = ["## Threads"]

    for cid in sorted(result.relevant_cids):
        thread_ids = mg.thread_for_cid(cid)
        if not thread_ids:
            continue

        # Find thread topic/goal from Open event
        goal = "Unknown goal"
        status = "Active"

        # Scan events in thread
        for eid in thread_ids:
            evt = eventlog.get(eid)
            kind = evt.get("kind")
            meta = evt.get("meta", {})

            if kind == "commitment_open":
                # Try to get goal from text or meta
                if meta.get("text"):
                    goal = meta["text"]
                elif "goal" in meta:  # some events might have goal field
                    goal = meta["goal"]

            if kind == "commitment_close":
                status = "Closed"

        # Concepts bound to this thread
        thread_concepts = cg.concepts_for_thread(mg, cid)
        concepts_str = ""
        if thread_concepts:
            # Only show top 3
            concepts_str = f" [{', '.join(thread_concepts[:3])}]"

        lines.append(f"- {cid}: {status} - {goal[:80]}{concepts_str}")

    return "\n".join(lines)


def _render_state_model(
    eventlog: EventLog, mirror: Mirror, result: RetrievalResult
) -> str:
    """Render identity, RSM, and open commitments (from Mirror)."""
    parts = []

    last_id = mirror.last_event_id
    if isinstance(last_id, int) and last_id > 0:
        parts.append(f"Ledger so far: events 1..{last_id} (total {last_id})")

    event_ids = result.event_ids or []
    if event_ids:
        start = min(event_ids)
        end = max(event_ids)
        count = len(event_ids)
        parts.append(
            f"Retrieval window this turn: events {start}..{end} ({count} events selected)"
        )

    # Identity
    ident = render_identity_claims(eventlog)
    if ident:
        parts.append(ident)

    # RSM
    snapshot = mirror.rsm_snapshot()
    rsm = render_rsm(snapshot)
    if rsm:
        parts.append(rsm)

    # Mirror Open Commitments (fast state)
    # Mirror has open_commitments property?
    # Mirror.open_commitments is a set of CIDs or dict?
    # Let's check Mirror. It usually tracks state.
    # If not, we use CommitmentManager (as in context_utils).
    # Let's stick to CommitmentManager via Mirror if possible, or direct.
    # context_utils uses CommitmentManager.

    # Ideally Mirror should expose this.
    # For now, let's reuse render_internal_goals logic but maybe generic?
    # Or just skip if not strictly required by prompt.
    # The proposal says "Section 3 ... Open commitments, stale flags".
    # Let's use Mirror for now.

    open_comms = mirror.get_open_commitment_events()
    if open_comms:
        cids = [
            e.get("meta", {}).get("cid")
            for e in open_comms
            if e.get("meta", {}).get("cid")
        ]
        if cids:
            parts.append(f"Open Commitments: {', '.join(sorted(cids))}")

    return "\n\n".join(parts)


def _render_evidence(event_ids: List[int], eventlog: EventLog) -> str:
    """Render chronological raw events."""
    if not event_ids:
        return ""

    lines = ["## Evidence"]

    # Sort chronologically
    chron_ids = sorted(event_ids)

    for eid in chron_ids:
        evt = eventlog.get(eid)
        kind = evt.get("kind")
        content = evt.get("content") or ""

        # Truncate content
        if len(content) > 300:
            content = content[:297] + "..."

        # Clean newlines for compact display?
        # content = content.replace("\n", "\\n")
        # Actually, formatted blocks are better readable.

        lines.append(f"[{eid}] {kind}: {content}")

    return "\n".join(lines)
