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
  claim types and, when both a proposal and ratification exist for a
  given token with no existing identity_adoption event, appends a single
  identity_adoption event.

All logic is ledger-only, replay-safe, and idempotent. No regex, no
heuristics – only structured parsing of claim content.
"""

from __future__ import annotations

import json
from typing import Dict, Set

from .event_log import EventLog


def maybe_append_identity_adoptions(eventlog: EventLog) -> None:
    """Append identity_adoption events deterministically where warranted.

    For each identity token:
      - At least one validated CLAIM:identity_proposal must exist.
      - At least one validated CLAIM:identity_ratify must exist.
      - No existing identity_adoption event for that token may exist yet.

    For each such token, append exactly one identity_adoption event with
    content:
      {"token": "<token>", "reason": "identity_proposal+ratification"}

    and meta:
      {"source": "identity_manager",
       "proposal_event_id": <int>,
       "ratify_event_id": <int>}

    Idempotent: calling this function multiple times over the same
    ledger will not emit duplicate identity_adoption events.
    """
    events = eventlog.read_all()

    # Track earliest proposal/ratification event id per token
    proposals: Dict[str, int] = {}
    ratifications: Dict[str, int] = {}
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

        if kind != "claim":
            continue

        meta = ev.get("meta") or {}
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
            if token not in proposals:
                proposals[token] = ev_id
        elif claim_type == "identity_ratify":
            if token not in ratifications:
                ratifications[token] = ev_id

    # Determine which tokens should gain an identity_adoption event.
    candidate_tokens = {
        tok
        for tok in proposals.keys() & ratifications.keys()
        if tok not in adopted_tokens
    }

    for token in sorted(candidate_tokens):
        proposal_id = proposals[token]
        ratify_id = ratifications[token]
        content_dict = {
            "token": token,
            "reason": "identity_proposal+ratification",
        }
        meta = {
            "source": "identity_manager",
            "proposal_event_id": proposal_id,
            "ratify_event_id": ratify_id,
        }
        eventlog.append(
            kind="identity_adoption",
            content=json.dumps(content_dict, sort_keys=True, separators=(",", ":")),
            meta=meta,
        )
