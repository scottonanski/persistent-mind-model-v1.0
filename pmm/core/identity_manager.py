# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/identity_manager.py
"""Deterministic identity adoption manager.

R06 v1: construct identity_adoption payloads from ledger structure and submit
them through the EventLog identity_adoption boundary. The manager does not
trust meta.validated and does not append the kind directly.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Set, Tuple

from .event_log import EventLog
from .identity_adoption import (
    ADOPTION_PROTOCOL_V1,
    IDENTITY_SUBJECT_ID_V1,
    canonical_identity_adoption_content,
    is_v1_authoritative_identity_adoption,
    parse_identity_anchor,
    parse_identity_claim_event,
    validate_identity_adoption_payload,
)


def maybe_append_identity_adoptions(eventlog: EventLog) -> None:
    """Append identity_adoption events deterministically where warranted.

    For each ``(pmm.self, token)`` that does not already have an r06.v1
    adoption, submit the earliest proposal/anchor/ratify chain that:

    - uses structurally valid identity claims (reparsed from content);
    - has a reflection carrying an exact v1 identity relation to that proposal;
    - has a ratification whose originating assistant is later than the anchor.

    The EventLog boundary revalidates the chain and enforces uniqueness.
    Incomplete chains are not attempts. Repeated scans are idempotent.
    """

    events = eventlog.read_all()
    proposals: Dict[str, List[dict]] = {}
    ratifications: Dict[str, List[dict]] = {}
    anchors_by_proposal: Dict[int, List[dict]] = {}
    adopted_tokens: Set[str] = set()

    for ev in events:
        kind = ev.get("kind")
        if kind == "identity_adoption":
            if not is_v1_authoritative_identity_adoption(ev, eventlog.get):
                continue
            try:
                data = json.loads(ev.get("content") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            token = data.get("token")
            subject_id = data.get("subject_id")
            if (
                isinstance(token, str)
                and token.strip()
                and isinstance(subject_id, str)
                and subject_id.strip() == IDENTITY_SUBJECT_ID_V1
            ):
                adopted_tokens.add(token.strip())
            continue

        if kind == "reflection":
            parsed_anchor = parse_identity_anchor(ev)
            if parsed_anchor is None:
                continue
            anchors_by_proposal.setdefault(
                parsed_anchor["proposal_event_id"], []
            ).append(parsed_anchor)
            continue

        parsed_claim = parse_identity_claim_event(ev)
        if parsed_claim is None or parsed_claim["origin_event_id"] is None:
            continue
        token = parsed_claim["token"]
        if parsed_claim["subject_id"] != IDENTITY_SUBJECT_ID_V1:
            continue
        if parsed_claim["claim_type"] == "identity_proposal":
            proposals.setdefault(token, []).append(parsed_claim)
        elif parsed_claim["claim_type"] == "identity_ratify":
            ratifications.setdefault(token, []).append(parsed_claim)

    def valid_sequence(token: str) -> Optional[Tuple[int, int, int, int, int]]:
        adoption_content = canonical_identity_adoption_content(
            token=token, subject_id=IDENTITY_SUBJECT_ID_V1
        )
        for proposal in proposals.get(token, []):
            proposal_id = proposal["id"]
            for anchor in anchors_by_proposal.get(proposal_id, []):
                if (
                    anchor["token"] != token
                    or anchor["subject_id"] != IDENTITY_SUBJECT_ID_V1
                ):
                    continue
                if anchor["id"] <= proposal_id:
                    continue
                for ratify in ratifications.get(token, []):
                    origin = ratify["origin_event_id"]
                    if origin is None:
                        continue
                    if (
                        proposal_id < anchor["id"] < ratify["id"]
                        and origin > anchor["id"]
                    ):
                        sequence = (
                            proposal_id,
                            anchor["id"],
                            ratify["id"],
                            proposal["origin_event_id"],
                            origin,
                        )
                        candidate_meta = {
                            "adoption_protocol": ADOPTION_PROTOCOL_V1,
                            "proposal_event_id": sequence[0],
                            "anchor_event_id": sequence[1],
                            "anchor_kind": "reflection",
                            "ratify_event_id": sequence[2],
                            "proposal_origin_event_id": sequence[3],
                            "ratify_origin_event_id": sequence[4],
                        }
                        if validate_identity_adoption_payload(
                            adoption_content, candidate_meta, eventlog.get
                        ).ok:
                            return sequence
        return None

    candidate_tokens = sorted(
        (proposals.keys() & ratifications.keys()) - adopted_tokens
    )
    for token in candidate_tokens:
        sequence = valid_sequence(token)
        if sequence is None:
            continue
        proposal_id, anchor_id, ratify_id, proposal_origin, ratify_origin = sequence
        eventlog.append_identity_adoption(
            content=canonical_identity_adoption_content(
                token=token, subject_id=IDENTITY_SUBJECT_ID_V1
            ),
            meta={
                "source": "identity_manager",
                "adoption_protocol": ADOPTION_PROTOCOL_V1,
                "proposal_event_id": proposal_id,
                "anchor_event_id": anchor_id,
                "anchor_kind": "reflection",
                "ratify_event_id": ratify_id,
                "proposal_origin_event_id": proposal_origin,
                "ratify_origin_event_id": ratify_origin,
            },
        )
