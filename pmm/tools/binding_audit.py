# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tools/binding_audit.py
"""Audit and backfill CTL bindings for claim events.

Deterministically identifies claim events that are missing a corresponding
`concept_bind_event` and can emit backfill events to restore CTL coverage.

Intended for maintenance/CLI use, not hot-path runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List

from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph


@dataclass(frozen=True)
class BindingGap:
    """Represents a missing CTL binding for a ledger event."""

    event_id: int
    token: str
    reason: str = "claim_missing_binding"


def _claim_token(event: dict) -> str | None:
    """Extract the claim type token from a claim event content."""
    if event.get("kind") != "claim":
        return None
    content = event.get("content") or ""
    if not content.startswith("CLAIM:") or "=" not in content:
        return None
    body = content[len("CLAIM:") :]
    token_part = body.split("=", 1)[0].strip()
    return token_part or None


def _claim_token(event: dict) -> str | None:
    """Extract the claim type token from a claim event content."""
    if event.get("kind") != "claim":
        return None
    content = event.get("content") or ""
    if not content.startswith("CLAIM:") or "=" not in content:
        return None
    body = content[len("CLAIM:") :]
    token_part = body.split("=", 1)[0].strip()
    return token_part or None


def audit_bindings(eventlog: EventLog) -> List[BindingGap]:
    """Return a deterministic list of missing CTL bindings for critical events."""
    events = eventlog.read_all()
    cg = ConceptGraph(eventlog)
    cg.rebuild(events)

    gaps: List[BindingGap] = []
    for ev in events:
        token = _claim_token(ev)
        if token:
            bound_ids = cg.events_for_concept(token)
            if ev["id"] not in bound_ids:
                gaps.append(
                    BindingGap(
                        event_id=ev["id"],
                        token=token,
                        reason="claim_missing_binding",
                    )
                )
            continue
        # Identity/policy/commitment bindings via meta tokens
        meta = ev.get("meta") or {}
        # Identity tokens
        ident_tok = meta.get("identity_token")
        if isinstance(ident_tok, str) and ident_tok:
            bound_ids = cg.events_for_concept(ident_tok)
            if ev["id"] not in bound_ids:
                gaps.append(
                    BindingGap(event_id=ev["id"], token=ident_tok, reason="identity")
                )
        # Policy tokens
        policy_tok = meta.get("policy_token")
        if isinstance(policy_tok, str) and policy_tok:
            bound_ids = cg.events_for_concept(policy_tok)
            if ev["id"] not in bound_ids:
                gaps.append(
                    BindingGap(event_id=ev["id"], token=policy_tok, reason="policy")
                )
        # Commitment/thread tokens
        cid = meta.get("cid")
        if isinstance(cid, str) and cid:
            commit_tok = f"commitment.{cid}"
            bound_ids = cg.events_for_concept(commit_tok)
            if ev["id"] not in bound_ids:
                gaps.append(
                    BindingGap(event_id=ev["id"], token=commit_tok, reason="commitment")
                )
    # Stable ordering for reproducibility
    gaps.sort(key=lambda g: (g.event_id, g.token))
    return gaps


def backfill_bindings(eventlog: EventLog, gaps: List[BindingGap]) -> List[int]:
    """Append deterministic concept_bind_event entries for each gap.

    Idempotent: re-checks each gap against the live ConceptGraph before writing.

    Returns list of appended event IDs.
    """
    if not gaps:
        return []

    cg = ConceptGraph(eventlog)
    cg.rebuild(eventlog.read_all())
    appended: List[int] = []

    for gap in gaps:
        # Ensure event still exists
        ev = eventlog.get(gap.event_id)
        if not ev:
            continue
        token = gap.token
        if not token:
            continue
        already_bound = gap.event_id in cg.events_for_concept(token)
        if already_bound:
            continue
        bind_content = json.dumps(
            {
                "event_id": gap.event_id,
                "tokens": [token],
                "relation": "describes",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        bind_id = eventlog.append(
            kind="concept_bind_event",
            content=bind_content,
            meta={"source": "binding_audit", "reason": gap.reason},
        )
        appended.append(bind_id)
        # Keep local projection up to date to avoid duplicate writes in the same run
        cg.sync(
            {
                "id": bind_id,
                "kind": "concept_bind_event",
                "content": bind_content,
                "meta": {"source": "binding_audit", "reason": gap.reason},
            }
        )

    return appended
