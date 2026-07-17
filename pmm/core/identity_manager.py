# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/identity_manager.py
"""Deterministic identity adoption manager.

Implements the Option C protocol:

- Identity proposals and ratifications are expressed as structured CLAIMs
  written into the ledger:

    CLAIM:identity_proposal={"token":"identity.Echo"}
    CLAIM:identity_ratify={"token":"identity.Echo"}

- This module scans the ledger for validated claim events with those
  claim types and requires an ordered proposal -> reflection/commitment ->
  ratification sequence for a given token. When that sequence exists and
  no identity_adoption event exists for the token, it appends one.

All logic is ledger-only, replay-safe, and idempotent. No regex, no
heuristics – only structured parsing of claim content.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from typing import Dict, List, Optional, Set, Tuple

from .event_log import EventLog


def maybe_append_identity_adoptions(eventlog: EventLog) -> None:
    """Append identity_adoption events deterministically where warranted.

    For each identity token:
      - A validated CLAIM:identity_proposal must exist.
      - A reflection or commitment lifecycle event must follow it.
      - A validated CLAIM:identity_ratify for the same token must follow
        that anchor event.
      - No existing identity_adoption event for that token may exist yet.

    For each such token, append exactly one identity_adoption event with
    content:
      {"token": "<token>",
       "reason": "identity_proposal+anchor+ratification"}

    and meta:
      {"source": "identity_manager",
       "proposal_event_id": <int>,
       "anchor_event_id": <int>,
       "anchor_kind": <str>,
       "ratify_event_id": <int>}

    Idempotent: calling this function multiple times over the same
    ledger will not emit duplicate identity_adoption events.
    """
    events = eventlog.read_all()

    proposals: Dict[str, List[int]] = {}
    ratifications: Dict[str, List[int]] = {}
    anchor_events: List[Tuple[int, str]] = []
    adopted_tokens: Set[str] = set()

    for ev in events:
        kind = ev.get("kind")
        if kind == "identity_adoption":
            # Existing adoption – record token so we do not re-emit.
            try:
                data = json.loads(ev.get("content") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            token = data.get("token")
            if isinstance(token, str) and token.strip():
                adopted_tokens.add(token.strip())
            continue

        if kind in {"reflection", "commitment_open", "commitment_close"}:
            ev_id = ev.get("id")
            if isinstance(ev_id, int):
                anchor_events.append((ev_id, str(kind)))
            continue

        if kind != "claim":
            continue

        meta = ev.get("meta") or {}
        if meta.get("validated") is not True:
            continue
        claim_type = meta.get("claim_type")
        if claim_type not in {"identity_proposal", "identity_ratify"}:
            continue

        content = ev.get("content") or ""
        if not content.startswith("CLAIM:"):
            # Not in the expected structured form; skip.
            continue
        try:
            head, payload = content.split("=", 1)
        except ValueError:
            continue
        # Optional consistency check: header type should match meta claim_type.
        header_type = head.removeprefix("CLAIM:").strip()
        if header_type and header_type != str(claim_type):
            # Inconsistent header/meta – ignore to preserve determinism.
            continue
        try:
            data = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        token = data.get("token")
        if not isinstance(token, str) or not token.strip():
            continue
        token = token.strip()

        ev_id = ev.get("id")
        if not isinstance(ev_id, int):
            continue

        if claim_type == "identity_proposal":
            proposals.setdefault(token, []).append(ev_id)
        elif claim_type == "identity_ratify":
            ratifications.setdefault(token, []).append(ev_id)

    anchor_ids = [event_id for event_id, _ in anchor_events]

    def valid_sequence(token: str) -> Optional[Tuple[int, int, str, int]]:
        """Return the earliest deterministic proposal/anchor/ratify tuple."""

        for proposal_id in proposals.get(token, []):
            anchor_index = bisect_right(anchor_ids, proposal_id)
            if anchor_index >= len(anchor_events):
                continue
            anchor_id, anchor_kind = anchor_events[anchor_index]
            for ratify_id in ratifications.get(token, []):
                if anchor_id < ratify_id:
                    return proposal_id, anchor_id, anchor_kind, ratify_id
        return None

    candidate_tokens = sorted(
        (proposals.keys() & ratifications.keys()) - adopted_tokens
    )
    for token in candidate_tokens:
        sequence = valid_sequence(token)
        if sequence is None:
            continue
        proposal_id, anchor_id, anchor_kind, ratify_id = sequence
        content_dict = {
            "token": token,
            "reason": "identity_proposal+anchor+ratification",
        }
        meta = {
            "source": "identity_manager",
            "proposal_event_id": proposal_id,
            "anchor_event_id": anchor_id,
            "anchor_kind": anchor_kind,
            "ratify_event_id": ratify_id,
        }
        eventlog.append(
            kind="identity_adoption",
            content=json.dumps(content_dict, sort_keys=True, separators=(",", ":")),
            meta=meta,
        )
