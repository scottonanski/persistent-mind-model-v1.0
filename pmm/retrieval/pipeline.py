# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Deterministic retrieval pipeline for PMM.

Orchestrates ConceptGraph, MemeGraph, and Vector search to select
relevant context for a turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.core.meme_graph import MemeGraph
from pmm.retrieval.vector import select_by_vector, select_by_concepts


@dataclass
class RetrievalConfig:
    """Configuration for the retrieval pipeline."""

    limit_total_events: int = 120
    limit_vector_events: int = 10
    limit_concept_events: int = 30
    graph_expansion_depth: int = 1
    recent_event_tail: int = 500
    summary_event_kinds: List[str] = field(default_factory=lambda: ["lifetime_memory"])
    summary_vector_limit: int = 6
    summary_event_scan_limit: Optional[int] = None
    vector_candidate_cap: int = 400
    sticky_concepts: List[str] = field(default_factory=lambda: ["user.identity"])

    # Concepts to always include in seeding
    always_include_concepts: List[str] = field(default_factory=list)

    # Force-inclusion of critical CTL concepts (identity/roles/commitments/policies)
    force_concept_prefixes: List[str] = field(
        default_factory=lambda: ["identity.", "role.", "policy.", "commitment.", "governance."]
    )
    force_concept_limit: int = 6

    # Whether to perform vector search
    enable_vector_search: bool = True
    enable_summary_vector_search: bool = True


@dataclass
class RetrievalResult:
    """Result of the retrieval pipeline."""

    event_ids: List[int]
    relevant_cids: List[str]
    active_concepts: List[str]


def run_retrieval_pipeline(
    *,
    query_text: str,
    eventlog: EventLog,
    concept_graph: ConceptGraph,
    meme_graph: MemeGraph,
    config: RetrievalConfig,
    user_event: Optional[Dict[str, Any]] = None,
) -> RetrievalResult:
    """Execute the deterministic retrieval pipeline.

    Steps:
    1. Concept Seeding: specific concepts from user event meta or config.
    2. CTL Selection: get events and threads bound to seeded concepts.
    3. Vector Selection: get events by semantic similarity.
    4. Graph Expansion: expand selection via MemeGraph.
    5. Merge & Sort: produce final stable list.
    """
    # 1. Concept Seeding
    seed_concepts: Set[str] = set(config.always_include_concepts)
    sticky_tokens: Set[str] = set(config.sticky_concepts or [])
    seed_concepts.update(sticky_tokens)

    # Extract from user event meta if present (deterministic)
    if user_event:
        meta = user_event.get("meta", {})
        # e.g. explicit "concepts" field in meta, or derived from "concept_ops"
        # For now, we assume meta might have "relevant_concepts"
        if "relevant_concepts" in meta and isinstance(meta["relevant_concepts"], list):
            seed_concepts.update(meta["relevant_concepts"])

    seed_concepts_list = sorted(seed_concepts)

    # 2. CTL Selection
    ctl_event_ids: Set[int] = set()
    relevant_cids: Set[str] = set()
    sticky_event_ids: Set[int] = set()
    forced_event_ids: Set[int] = set()

    if seed_concepts_list:
        # Get events bound to concepts via live ConceptGraph projection only.
        bound_ids = select_by_concepts(
            concept_tokens=seed_concepts_list,
            concept_graph=concept_graph,
            limit=max(config.limit_concept_events, config.limit_total_events),
        )
        ctl_event_ids.update(bound_ids)

        # Get threads bound to concepts
        for token in seed_concepts_list:
            cids = concept_graph.threads_for_concept(meme_graph, token)
            relevant_cids.update(cids)

    if sticky_tokens:
        sticky_bound = select_by_concepts(
            concept_tokens=sorted(sticky_tokens),
            concept_graph=concept_graph,
            limit=max(config.limit_concept_events, config.limit_total_events),
        )
        sticky_event_ids.update(sticky_bound)

    # Force-include critical CTL concepts (identity/roles/commitments/policies).
    forced_tokens: List[str] = []
    prefixes = tuple(config.force_concept_prefixes or [])
    for tok in seed_concepts_list:
        if tok == "user.identity":
            forced_tokens.append(tok)
            continue
        if prefixes and tok.startswith(prefixes):
            forced_tokens.append(tok)

    for tok in forced_tokens:
        forced_event_ids.update(
            select_by_concepts(
                concept_tokens=[tok],
                concept_graph=concept_graph,
                limit=config.force_concept_limit,
            )
        )

    # 3. Vector Selection
    vector_event_ids: Set[int] = set()
    summary_vector_ids: Set[int] = set()
    summary_expanded_ids: Set[int] = set()
    if config.enable_vector_search and query_text:
        # Use a bounded tail of recent events to keep vector search scalable.
        tail_events = eventlog.read_tail(config.recent_event_tail)
        vec_ids, _ = select_by_vector(
            events=tail_events,
            query_text=query_text,
            limit=config.limit_vector_events,
            # Use defaults for model/dims for now
            cap=config.vector_candidate_cap,
        )
        vector_event_ids.update(vec_ids)

        if config.enable_summary_vector_search and config.summary_event_kinds:
            summary_events: List[Dict] = []
            for kind in config.summary_event_kinds:
                summary_events.extend(
                    eventlog.read_by_kind(
                        kind,
                        limit=config.summary_event_scan_limit,
                        reverse=False,
                    )
                )
            summary_events = sorted(summary_events, key=lambda ev: int(ev.get("id", 0)))
            if summary_events:
                s_vec_ids, _ = select_by_vector(
                    events=summary_events,
                    query_text=query_text,
                    limit=config.summary_vector_limit,
                    kinds=config.summary_event_kinds,
                    cap=len(summary_events),
                )
                summary_vector_ids.update(s_vec_ids)
                summary_expanded_ids.update(summary_vector_ids)
                for sid in s_vec_ids:
                    ev = eventlog.get(sid) or {}
                    meta = ev.get("meta") or {}
                    sample_ids = meta.get("sample_ids") or []
                    for mid in sample_ids:
                        try:
                            mid_int = int(mid)
                        except Exception:
                            continue
                        if eventlog.exists(mid_int):
                            summary_expanded_ids.add(mid_int)

    # 4. Graph Expansion (MemeGraph)
    # We want to expand around the seed events (CTL + Vector).
    # AND include full threads for any relevant CIDs.

    base_ids = (
        ctl_event_ids.union(vector_event_ids)
        .union(summary_expanded_ids)
        .union(sticky_event_ids)
        .union(forced_event_ids)
    )
    expanded_ids: Set[int] = set(base_ids)

    # Expand generic neighbors
    for eid in list(base_ids):
        # Immediate neighbors
        neighbors = meme_graph.neighbors(eid, direction="both")
        expanded_ids.update(neighbors)

        # Also, if this event is part of any thread, mark that CID as relevant
        # event_cids = meme_graph.cids_for_event(eid)
        # relevant_cids.update(event_cids)
        # (Optional: do we want to drag in every thread touched by a vector match?
        #  Maybe too noisy. Let's stick to explicitly concept-linked threads for now
        #  plus threads explicitly mentioned in meta if any.)

    # Expand full threads for relevant CIDs
    for cid in relevant_cids:
        thread_events = meme_graph.thread_for_cid(cid)
        expanded_ids.update(thread_events)
        # Also expand around thread events?
        # "Use MemeGraph to expand/shape those threads."
        # MemeGraph.subgraph_for_cid does exactly this (thread + neighbors)
        subgraph = meme_graph.subgraph_for_cid(cid)
        expanded_ids.update(subgraph)

    # 5. Finalize
    # Filter valid IDs (sanity check) and sort
    # all_events_map = {e["id"]: e for e in eventlog.read_all()}  # expensive?
    # Actually we just need IDs to be valid.
    # If we trust MemeGraph/ConceptGraph/Vector, they return valid IDs.

    forced_sorted = sorted(forced_event_ids, reverse=True)
    sticky_sorted = [
        eid for eid in sorted(sticky_event_ids, reverse=True) if eid not in forced_event_ids
    ]
    context_candidates = sorted(
        expanded_ids - forced_event_ids - sticky_event_ids, reverse=True
    )
    context_limit = max(
        config.limit_total_events - len(forced_sorted) - len(sticky_sorted), 0
    )
    context_final = context_candidates[:context_limit]

    # Combine with forced first to guarantee inclusion, then sticky anchors.
    final_ids = forced_sorted + sticky_sorted + context_final
    if len(final_ids) > config.limit_total_events:
        final_ids = final_ids[: config.limit_total_events]

    # For active_concepts, we return the seed concepts.
    # We could also verify which concepts are actually present in the final selection.

    return RetrievalResult(
        event_ids=final_ids,
        relevant_cids=sorted(relevant_cids),
        active_concepts=seed_concepts_list,
    )
