# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/context_builder.py
from __future__ import annotations

import json
from typing import Any, Dict, List

from pmm.core.event_log import EventLog
from pmm.core.ledger_mirror import LedgerMirror
from pmm.core.commitment_manager import CommitmentManager
from pmm.core.meme_graph import MemeGraph


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

    Includes only user/assistant messages, capped to the last `limit` pairs.
    """
    # Override limit from ledger-backed retrieval config if present
    cfg = _last_retrieval_config(eventlog)
    if cfg and cfg.get("strategy") == "fixed":
        try:
            lim = int(cfg.get("limit"))
            if lim > 0:
                limit = lim
        except Exception:
            pass
    # Over-fetch recent events and then filter to message kinds
    rows = list(eventlog.read_tail(limit * 8))
    lines: List[str] = []
    for e in rows:
        kind = e.get("kind")
        if kind in ("user_message", "assistant_message"):
            lines.append(f"{kind}: {e.get('content','')}")
    tail = lines[-(limit * 2) :]
    body = "\n".join(tail)

    mirror = LedgerMirror(eventlog, listen=False)
    snapshot = mirror.rsm_snapshot()
    identity_block = _render_identity_claims(eventlog)
    rsm_block = _render_rsm(snapshot)
    goals_block = _render_internal_goals(eventlog)
    graph_block = _render_graph_context(eventlog) if not tail else ""

    extras = "\n".join(
        section
        for section in (identity_block, rsm_block, goals_block, graph_block)
        if section
    )
    if body and extras:
        return f"{body}\n\n{extras}"
    if extras:
        return extras
    return body


def _render_identity_claims(eventlog: EventLog) -> str:
    """Render identity claims (e.g., name) from ledger claim events.

    Returns empty string if no identity claims exist.
    """
    events = eventlog.read_all()
    identity_facts: Dict[str, str] = {}

    for event in events:
        if event.get("kind") != "claim":
            continue
        meta = event.get("meta") or {}
        claim_type = meta.get("claim_type")

        # Extract name from name_change claims
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


def _render_rsm(snapshot: Dict[str, Any]) -> str:
    if not snapshot:
        return ""
    tendencies = snapshot.get("behavioral_tendencies") or {}
    gaps = snapshot.get("knowledge_gaps") or []
    meta_patterns = snapshot.get("interaction_meta_patterns") or []
    # If uniqueness is the only tendency and no other signals, hide RSM block
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


def _render_internal_goals(eventlog: EventLog) -> str:
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


def _render_graph_context(eventlog: EventLog) -> str:
    """Render memegraph structural context for model introspection.

    Deterministically rebuilds graph from ledger and exposes:
    - Connection density (edges/nodes ratio)
    - Active commitment thread depths

    Returns empty string if graph has insufficient data (<5 nodes).
    """
    mg = MemeGraph(eventlog)
    mg.rebuild(eventlog.read_all())
    stats = mg.graph_stats()

    # Only render if graph has meaningful structure
    if stats["nodes"] < 5:
        return ""

    lines = []

    # Minimal line for small graphs to keep context size bounded
    if stats["nodes"] <= 8:
        lines.append(f"Graph: {stats['nodes']} nodes, {stats['edges']} edges")
    else:
        lines.append(
            f"Graph Context:\n- Connections: {stats['edges']} edges, {stats['nodes']} nodes"
        )

    # Build thread depth info for open commitments
    manager = CommitmentManager(eventlog)
    open_comms = manager.get_open_commitments()
    thread_parts: List[str] = []

    for comm in open_comms[:3]:  # Limit to 3 most recent
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
