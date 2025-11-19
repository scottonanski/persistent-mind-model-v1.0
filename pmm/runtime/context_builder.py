# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/context_builder.py
from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror


def _last_retrieval_config(eventlog: EventLog) -> dict | None:
    """Return last retrieval config from ledger config events, if any.

    Expected content JSON: {"type":"retrieval", "strategy":"fixed", "limit": N}
    """
    cfg = None
    for e in eventlog.read_all():
        if e.get("kind") != "config":
            continue
        try:
            data = json.loads(e.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == "retrieval":
            cfg = data
    return cfg


def build_context(eventlog: EventLog, limit: int = 5) -> str:
    """Deterministically reconstruct a short context window from the ledger.

    Compatibility wrapper: uses the new pmm.retrieval.pipeline and pmm.runtime.context_renderer.
    """
    # Override limit from ledger-backed retrieval config if present
    cfg_json = _last_retrieval_config(eventlog)
    if cfg_json and cfg_json.get("strategy") == "fixed":
        try:
            lim = int(cfg_json.get("limit"))
            if lim > 0:
                limit = lim
        except Exception:
            pass

    from pmm.retrieval.pipeline import run_retrieval_pipeline, RetrievalConfig
    from pmm.runtime.context_renderer import render_context
    from pmm.core.concept_graph import ConceptGraph
    from pmm.core.meme_graph import MemeGraph

    # Rebuild projections on demand for this one-off call (legacy tests usually use fresh logs)
    cg = ConceptGraph(eventlog)
    cg.rebuild(eventlog.read_all())
    mg = MemeGraph(eventlog)
    mg.rebuild(eventlog.read_all())
    mirror = Mirror(eventlog, enable_rsm=True, listen=False)

    # Configure pipeline to mimic fixed window (no vector, just recency)
    # By default pipeline does graph expansion, but if we set concepts=[], it relies on
    # fallback or vector. If vector disabled, what does it select?
    # Pipeline selects from: CTL + Vector.
    # If both empty, it might return nothing?
    # We need a fallback "recent events" selection if pipeline yields nothing?
    # Pipeline doc says: "Steps ... Merge & Sort".
    # If seeds empty and vector disabled, base_ids is empty.

    # We need to manually feed recent IDs if pipeline doesn't handle "just give me recent".
    # The new pipeline is Concept-First.
    # "Legacy cleanup ... Remove ... path that Ignores CTL".
    # So `build_context` SHOULD use CTL.
    # But if no concepts are defined, it might return empty context?
    # That might break tests that expect "user: u0".

    # Let's enable vector search if we want "search"? No, "fixed" means no vector.
    # Let's explicitly add the last N events to the selection?
    # This violates "Concept-First" but is necessary for basic "chat" functionality
    # when no concepts exist yet (bootstrapping).

    config = RetrievalConfig(
        limit_total_events=limit, enable_vector_search=False, always_include_concepts=[]
    )

    result = run_retrieval_pipeline(
        query_text="", eventlog=eventlog, concept_graph=cg, meme_graph=mg, config=config
    )

    # Fallback: if result is empty, grab recent messages (bootstrap)
    if not result.event_ids:
        events = eventlog.read_tail(limit * 2)  # read a bit more to filter
        recent_ids = []
        for e in reversed(events):
            if e.get("kind") in ("user_message", "assistant_message"):
                recent_ids.append(int(e["id"]))
            if len(recent_ids) >= limit:
                break
        result.event_ids = sorted(recent_ids, reverse=True)

    return render_context(
        result=result, eventlog=eventlog, concept_graph=cg, meme_graph=mg, mirror=mirror
    )
