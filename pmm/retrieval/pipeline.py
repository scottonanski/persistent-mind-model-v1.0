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

    limit_total_events: int = 50
    limit_vector_events: int = 10
    limit_concept_events: int = 20
    graph_expansion_depth: int = 1

    # Concepts to always include in seeding
    always_include_concepts: List[str] = field(default_factory=list)

    # Whether to perform vector search
    enable_vector_search: bool = True


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

    if seed_concepts_list:
        # Get events bound to concepts
        bound_ids = select_by_concepts(
            concept_tokens=seed_concepts_list,
            concept_graph=concept_graph,
            events=eventlog.read_all(),  # optimization: pass reference or iterator
            limit=config.limit_concept_events,
        )
        ctl_event_ids.update(bound_ids)

        # Get threads bound to concepts
        for token in seed_concepts_list:
            cids = concept_graph.threads_for_concept(meme_graph, token)
            relevant_cids.update(cids)

    # 3. Vector Selection
    vector_event_ids: Set[int] = set()
    if config.enable_vector_search and query_text:
        vec_ids, _ = select_by_vector(
            events=eventlog.read_all(),
            query_text=query_text,
            limit=config.limit_vector_events,
            # Use defaults for model/dims for now
        )
        vector_event_ids.update(vec_ids)

    # 4. Graph Expansion (MemeGraph)
    # We want to expand around the seed events (CTL + Vector).
    # AND include full threads for any relevant CIDs.

    base_ids = ctl_event_ids.union(vector_event_ids)
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

    final_ids = sorted(expanded_ids, reverse=True)  # Most recent first
    if len(final_ids) > config.limit_total_events:
        final_ids = final_ids[: config.limit_total_events]

    # For active_concepts, we return the seed concepts.
    # We could also verify which concepts are actually present in the final selection.

    return RetrievalResult(
        event_ids=final_ids,
        relevant_cids=sorted(relevant_cids),
        active_concepts=seed_concepts_list,
    )
