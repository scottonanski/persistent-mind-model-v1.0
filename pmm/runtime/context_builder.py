# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/context_builder.py
from __future__ import annotations

import json
from typing import List

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.runtime.context_utils import (
    render_graph_context,
    render_identity_claims,
    render_internal_goals,
    render_rsm,
)


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

    mirror = Mirror(eventlog, enable_rsm=True, listen=False)
    snapshot = mirror.rsm_snapshot()
    identity_block = render_identity_claims(eventlog)
    rsm_block = render_rsm(snapshot)
    goals_block = render_internal_goals(eventlog)
    graph_block = render_graph_context(eventlog) if not tail else ""

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
