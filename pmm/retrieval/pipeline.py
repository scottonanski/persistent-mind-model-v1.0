# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Deterministic retrieval pipeline for PMM.

Orchestrates ConceptGraph, MemeGraph, and Vector search to select
relevant context for a turn.
"""

from __future__ import annotations

import math
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
    thread_event_limit: int = 12
    concept_thread_limit: int = 8
    graph_expansion_depth: int = 1
    recent_event_tail: int = 500
    summary_event_kinds: List[str] = field(default_factory=lambda: ["lifetime_memory"])
    summary_vector_limit: int = 6
    summary_event_scan_limit: Optional[int] = None
    vector_candidate_cap: int = 400
    sticky_concepts: List[str] = field(default_factory=lambda: ["user.identity"])
    include_summary_events: bool = True
    summary_pin_limit: int = 2
    dynamic_cap_growth: bool = True
    cap_growth_factor: float = 0.05
    cap_total_max: int = 240

    # Concepts to always include in seeding
    always_include_concepts: List[str] = field(default_factory=list)

    # Force-inclusion of critical CTL concepts (identity/roles/commitments/policies)
    force_concept_prefixes: List[str] = field(
        default_factory=lambda: [
            "identity.",
            "role.",
            "policy.",
            "commitment.",
            "governance.",
        ]
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
    total_events = eventlog.count() if hasattr(eventlog, "count") else 0

    def _grow_cap(base: int, max_cap: int) -> int:
        if not config.dynamic_cap_growth:
            return base
        factor = float(config.cap_growth_factor)
        return min(
            int(max_cap),
            int(base + math.log1p(max(total_events, 0)) * factor * base),
        )

    limit_total_events = min(
        _grow_cap(config.limit_total_events, config.cap_total_max),
        config.cap_total_max,
    )
    thread_event_limit = _grow_cap(config.thread_event_limit, config.cap_total_max)
    concept_thread_limit = max(1, int(config.concept_thread_limit))

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

        # Prefer explicit concept->CID bindings over event-only bindings
        bound_cids = concept_graph.resolve_cids_for_concepts(seed_concepts_list)
        if bound_cids:
            # Respect per-concept cap by truncating sorted bound_cids
            sorted_cids = sorted(bound_cids)
            relevant_cids.update(sorted_cids[:concept_thread_limit])

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

    # Topological boost based on ConceptGraph roots/tails.
    # For seeded concepts, ensure that the earliest and/or latest evidence
    # bound to those tokens is available in the forced bucket.
    if seed_concepts_list:
        topology_budget = max(4, min(12, limit_total_events // 10))
        added_from_topology = 0
        for tok in seed_concepts_list:
            if added_from_topology >= topology_budget:
                break

            root_eid = concept_graph.root_event_id(tok)
            tail_eid = concept_graph.tail_event_id(tok)
            kind = concept_graph.concept_kind(tok)

            ids_to_add: List[int] = []
            # For identity/policy/governance/ontology kinds, prefer both origin and state.
            if kind in ("identity", "policy", "governance", "ontology"):
                if isinstance(root_eid, int):
                    ids_to_add.append(root_eid)
                if isinstance(tail_eid, int) and tail_eid != root_eid:
                    ids_to_add.append(tail_eid)
            elif kind:
                # For other concept kinds, a tail binding is usually enough for continuity.
                if isinstance(tail_eid, int):
                    ids_to_add.append(tail_eid)

            for eid in ids_to_add:
                if added_from_topology >= topology_budget:
                    break
                if eventlog.exists(eid):
                    forced_event_ids.add(eid)
                    added_from_topology += 1

    # 3. Vector Selection
    vector_event_ids: Set[int] = set()
    summary_vector_ids: Set[int] = set()
    summary_expanded_ids: Set[int] = set()
    summary_pinned_ids: Set[int] = set()

    # Vector stage becomes a refiner over already selected slices only
    def _refine_with_vector(candidate_ids: Set[int], limit: int) -> Set[int]:
        if not config.enable_vector_search or not query_text:
            return set()
        if not candidate_ids:
            return set()
        events_data: List[Dict] = []
        for eid in sorted(candidate_ids):
            ev = eventlog.get(int(eid)) or {}
            ev["id"] = int(eid)
            events_data.append(ev)
        vec_ids, _ = select_by_vector(
            events=events_data,
            query_text=query_text,
            limit=min(limit, len(events_data)),
            cap=len(events_data),
        )
        return set(vec_ids)

    # 3a. Thread-first selection (concept -> CID -> slices)
    thread_expanded_ids: Set[int] = set()
    if relevant_cids:
        for cid in sorted(relevant_cids):
            slice_ids = meme_graph.get_thread_slice(cid, limit=thread_event_limit)
            thread_expanded_ids.update(slice_ids)

    # 3b. Optional vector refinement over thread slices
    if config.enable_vector_search and query_text:
        refined_ids = _refine_with_vector(
            thread_expanded_ids.union(ctl_event_ids).union(sticky_event_ids),
            config.limit_vector_events,
        )
        vector_event_ids.update(refined_ids)

    # 3c. Summary vector search (unchanged but bounded to summaries)
    if (
        config.enable_vector_search
        and config.enable_summary_vector_search
        and query_text
    ):
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
                cids = meta.get("cids") or []
                for mid in sample_ids:
                    try:
                        mid_int = int(mid)
                    except Exception:
                        continue
                    if eventlog.exists(mid_int):
                        summary_expanded_ids.add(mid_int)
                # Expand via cids to pull deterministic slices
                for cid in cids:
                    slice_ids = meme_graph.get_thread_slice(
                        cid, limit=thread_event_limit
                    )
                    summary_expanded_ids.update(slice_ids)

    # Always pin recent summary/lifetime_memory events if configured
    if config.include_summary_events and config.summary_event_kinds:
        for kind in config.summary_event_kinds:
            pinned = eventlog.read_by_kind(
                kind,
                limit=max(1, int(config.summary_pin_limit)),
                reverse=True,
            )
            for ev in pinned:
                eid = int(ev.get("id", 0))
                summary_pinned_ids.add(eid)
                # Expand evidence tail via sample_ids when present
                meta = ev.get("meta") or {}
                for sid in meta.get("sample_ids", []) or []:
                    try:
                        sid_int = int(sid)
                    except Exception:
                        continue
                    if eventlog.exists(sid_int):
                        summary_expanded_ids.add(sid_int)

    # Structural lifetime_memory recall: for seeded concepts, also pin the
    # earliest lifetime_memory chunk that references them, if configurable.
    if config.summary_event_kinds and "lifetime_memory" in config.summary_event_kinds:
        lm_events = eventlog.read_by_kind("lifetime_memory", reverse=False)
        if lm_events and seed_concepts_list:
            # Map canonical tokens to earliest lifetime_memory id that mentions them
            earliest_lm_for_concept: Dict[str, int] = {}
            canonical_seeds = {
                concept_graph.canonical_token(tok) for tok in seed_concepts_list
            }
            for ev in lm_events:
                meta = ev.get("meta") or {}
                chunk_concepts = meta.get("concepts") or []
                if not chunk_concepts:
                    continue
                canonical_chunk = {
                    concept_graph.canonical_token(tok) for tok in chunk_concepts
                }
                overlap = canonical_seeds & canonical_chunk
                if not overlap:
                    continue
                ev_id = int(ev.get("id", 0))
                for canon in overlap:
                    if canon not in earliest_lm_for_concept:
                        earliest_lm_for_concept[canon] = ev_id
            for ev_id in earliest_lm_for_concept.values():
                if ev_id:
                    summary_pinned_ids.add(ev_id)

    # 4. Graph Expansion (MemeGraph)
    # We want to expand around the seed events (CTL + Vector).
    # AND include full threads for any relevant CIDs.

    thread_expanded_ids: Set[int] = set()

    base_ids = (
        ctl_event_ids.union(vector_event_ids)
        .union(summary_expanded_ids)
        .union(sticky_event_ids)
        .union(forced_event_ids)
        .union(thread_expanded_ids)
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
        thread_expanded_ids.update(thread_events)
        # Also expand around thread events?
        # "Use MemeGraph to expand/shape those threads."
        # MemeGraph.subgraph_for_cid does exactly this (thread + neighbors)
        subgraph = meme_graph.subgraph_for_cid(cid)
        expanded_ids.update(subgraph)
        thread_expanded_ids.update(subgraph)

    # 5. Finalize
    # Bucketed allocation: pinned (forced+sticky) > concept > thread > summary > vector > residual
    forced_sorted = sorted(forced_event_ids, reverse=True)
    sticky_sorted = [
        eid
        for eid in sorted(sticky_event_ids, reverse=True)
        if eid not in forced_event_ids
    ]
    summary_sorted = [
        eid
        for eid in sorted(summary_pinned_ids, reverse=True)
        if eid not in forced_event_ids and eid not in sticky_event_ids
    ]
    pinned_ids = forced_sorted + sticky_sorted + summary_sorted
    pinned_ids = pinned_ids[:limit_total_events]
    pinned_set = set(pinned_ids)

    concept_set = ctl_event_ids - pinned_set
    thread_set = thread_expanded_ids - pinned_set - concept_set
    summary_set = summary_expanded_ids - pinned_set - concept_set - thread_set
    vector_set = vector_event_ids - pinned_set - concept_set - thread_set - summary_set
    residual_set = (
        expanded_ids - pinned_set - concept_set - thread_set - summary_set - vector_set
    )

    concept_bucket = sorted(concept_set, reverse=True)
    thread_bucket = sorted(thread_set, reverse=True)
    summary_bucket = sorted(summary_set, reverse=True)
    vector_bucket = sorted(vector_set, reverse=True)
    residual_bucket = sorted(residual_set, reverse=True)

    final_ids = list(pinned_ids)
    remaining = max(limit_total_events - len(final_ids), 0)

    def _take(bucket: List[int]) -> None:
        nonlocal remaining
        if remaining <= 0:
            return
        take = bucket[:remaining]
        final_ids.extend(take)
        remaining -= len(take)

    _take(concept_bucket)
    _take(thread_bucket)
    _take(summary_bucket)
    _take(vector_bucket)
    _take(residual_bucket)

    # For active_concepts, we return the seed concepts.
    # We could also verify which concepts are actually present in the final selection.

    return RetrievalResult(
        event_ids=final_ids,
        relevant_cids=sorted(relevant_cids),
        active_concepts=seed_concepts_list,
    )
