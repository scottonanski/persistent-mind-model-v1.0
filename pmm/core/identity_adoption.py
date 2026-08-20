# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/identity_adoption.py
"""R06 v1 identity-adoption predicates shared by append and projections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable, Dict, Mapping, Optional

from .semantic_extractor import extract_claims

IDENTITY_SUBJECT_ID_V1 = "pmm.self"
ADOPTION_PROTOCOL_V1 = "r06.v1"
IDENTITY_ANCHOR_RELATION_V1 = "anchors_identity_for"
IDENTITY_ADOPTION_REASON_V1 = "identity_proposal+anchor+ratification"
IDENTITY_ADOPTION_VALIDATOR_SOURCE = "identity_adoption_validator"
IDENTITY_CLAIM_TYPES = frozenset({"identity_proposal", "identity_ratify"})
IDENTITY_ANCHOR_KEYS = frozenset(
    {"protocol", "relation", "subject_id", "token", "proposal_event_id"}
)
IDENTITY_ADOPTION_CONTENT_KEYS = frozenset({"token", "subject_id", "reason"})
IDENTITY_ADOPTION_REQUIRED_META_KEYS = frozenset(
    {
        "adoption_protocol",
        "proposal_event_id",
        "anchor_event_id",
        "anchor_kind",
        "ratify_event_id",
        "proposal_origin_event_id",
        "ratify_origin_event_id",
    }
)

GetEvent = Callable[[int], Optional[Dict[str, Any]]]


@dataclass(frozen=True)
class IdentityAdoptionValidation:
    ok: bool
    code: str
    message: str
    token: str = ""
    subject_id: str = ""
    proposal_event_id: Optional[int] = None
    anchor_event_id: Optional[int] = None
    ratify_event_id: Optional[int] = None


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _nonempty_stripped_string(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def identity_claim_structure_error(claim_type: str, data: Any) -> Optional[str]:
    """Return an error message if identity claim payload is not R06 v1 shape."""

    if not isinstance(data, dict):
        return "identity payload must be an object"

    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        return "identity token must be a non-empty string"

    subject_id = data.get("subject_id")
    if not isinstance(subject_id, str) or subject_id.strip() != IDENTITY_SUBJECT_ID_V1:
        return "identity subject_id must be pmm.self"

    if claim_type == "identity_ratify":
        unexpected = set(data) - {"token", "subject_id"}
        if unexpected:
            return "identity ratification contains unsupported fields"
        return None

    allowed = {"token", "subject_id", "description", "evidence_events"}
    unexpected = set(data) - allowed
    if unexpected:
        return "identity proposal contains unsupported fields"

    if "description" in data:
        description = data["description"]
        if not isinstance(description, str) or not description.strip():
            return "identity description must be a non-empty string"
    return None


def parse_identity_claim_event(event: Mapping[str, Any] | None) -> Optional[Dict[str, Any]]:
    """Parse a ledger claim as an identity proposal or ratification."""

    if not isinstance(event, Mapping) or event.get("kind") != "claim":
        return None
    content = event.get("content") or ""
    if not isinstance(content, str):
        return None
    try:
        extracted = extract_claims(content.splitlines())
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if len(extracted) != 1:
        return None
    header_type, data = extracted[0]
    meta = event.get("meta") or {}
    claim_type = meta.get("claim_type")
    if claim_type not in IDENTITY_CLAIM_TYPES:
        return None
    if header_type and header_type != str(claim_type):
        return None
    if identity_claim_structure_error(str(claim_type), data) is not None:
        return None
    event_id = _positive_int(event.get("id"))
    if event_id is None:
        return None
    return {
        "id": event_id,
        "claim_type": str(claim_type),
        "token": str(data["token"]).strip(),
        "subject_id": str(data["subject_id"]).strip(),
        "origin_event_id": _positive_int(meta.get("origin_event_id")),
        "data": data,
    }


def parse_identity_anchor(event: Mapping[str, Any] | None) -> Optional[Dict[str, Any]]:
    """Parse a reflection's nested R06 v1 identity-anchor relation."""

    if not isinstance(event, Mapping) or event.get("kind") != "reflection":
        return None
    event_id = _positive_int(event.get("id"))
    if event_id is None:
        return None
    meta = event.get("meta") or {}
    anchor = meta.get("identity_anchor")
    if not isinstance(anchor, dict) or set(anchor) != IDENTITY_ANCHOR_KEYS:
        return None
    if anchor.get("protocol") != ADOPTION_PROTOCOL_V1:
        return None
    if anchor.get("relation") != IDENTITY_ANCHOR_RELATION_V1:
        return None
    subject_id = _nonempty_stripped_string(anchor.get("subject_id"))
    token = _nonempty_stripped_string(anchor.get("token"))
    proposal_event_id = _positive_int(anchor.get("proposal_event_id"))
    if subject_id != IDENTITY_SUBJECT_ID_V1 or token is None or proposal_event_id is None:
        return None
    return {
        "id": event_id,
        "subject_id": subject_id,
        "token": token,
        "proposal_event_id": proposal_event_id,
    }


def attempted_identity_adoption_digest(content: str, meta: Mapping[str, Any]) -> str:
    """Stable digest of one identity_adoption attempt (no prev_hash)."""

    payload: Dict[str, Any] = {
        "kind": "identity_adoption",
        "content": content,
        "meta": dict(meta),
    }
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict):
        payload["content"] = parsed
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _fail(
    code: str,
    message: str,
    *,
    token: str = "",
    subject_id: str = "",
    proposal_event_id: Optional[int] = None,
    anchor_event_id: Optional[int] = None,
    ratify_event_id: Optional[int] = None,
) -> IdentityAdoptionValidation:
    return IdentityAdoptionValidation(
        False,
        code,
        message,
        token=token,
        subject_id=subject_id,
        proposal_event_id=proposal_event_id,
        anchor_event_id=anchor_event_id,
        ratify_event_id=ratify_event_id,
    )


def _assistant_origin_valid(
    origin: Mapping[str, Any] | None,
    *,
    origin_id: int,
    before_event_id: int,
    claim_type: str,
    claim_data: Mapping[str, Any],
) -> bool:
    if not isinstance(origin, Mapping):
        return False
    if origin.get("kind") != "assistant_message":
        return False
    loaded_id = _positive_int(origin.get("id"))
    if loaded_id != origin_id or origin_id >= before_event_id:
        return False
    content = origin.get("content")
    if not isinstance(content, str):
        return False
    try:
        emitted_claims = extract_claims(content.splitlines())
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    for emitted_type, emitted_data in emitted_claims:
        if emitted_type != claim_type:
            continue
        if emitted_data == dict(claim_data):
            return True
    return False


def _identity_proposal_evidence_valid(
    proposal: Mapping[str, Any],
    get_event: GetEvent,
) -> bool:
    """Reconstruct the ledger-existence portion of proposal validation."""

    data = proposal["data"]
    if "evidence_events" not in data:
        return True
    evidence = data["evidence_events"]
    if not isinstance(evidence, list):
        return False
    proposal_id = proposal["id"]
    for event_id in evidence:
        if _positive_int(event_id) is None:
            return False
        if event_id >= proposal_id or get_event(event_id) is None:
            return False
    return True


def validate_identity_adoption_payload(
    content: str,
    meta: Mapping[str, Any],
    get_event: GetEvent,
    *,
    adoption_id: Optional[int] = None,
) -> IdentityAdoptionValidation:
    """Validate an identity_adoption payload against ledger role constraints."""

    if not isinstance(content, str) or not isinstance(meta, Mapping):
        return _fail(
            "INVALID_IDENTITY_ADOPTION_STRUCTURE",
            "identity_adoption requires string content and object meta",
        )
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return _fail(
            "INVALID_IDENTITY_ADOPTION_STRUCTURE",
            "identity_adoption content must be JSON",
        )
    if not isinstance(data, dict) or set(data) != IDENTITY_ADOPTION_CONTENT_KEYS:
        return _fail(
            "INVALID_IDENTITY_ADOPTION_STRUCTURE",
            "identity_adoption content must contain only token, subject_id, reason",
        )
    token = _nonempty_stripped_string(data.get("token"))
    subject_id = _nonempty_stripped_string(data.get("subject_id"))
    if token is None:
        return _fail(
            "INVALID_IDENTITY_ADOPTION_STRUCTURE",
            "identity token must be a non-empty string",
        )
    if subject_id != IDENTITY_SUBJECT_ID_V1:
        return _fail(
            "IDENTITY_SUBJECT_MISMATCH",
            "identity subject_id must be pmm.self",
            token=token,
            subject_id=str(data.get("subject_id") or ""),
        )
    if data.get("reason") != IDENTITY_ADOPTION_REASON_V1:
        return _fail(
            "INVALID_IDENTITY_ADOPTION_STRUCTURE",
            "identity_adoption reason is not the v1 protocol reason",
            token=token,
            subject_id=subject_id,
        )
    if meta.get("adoption_protocol") != ADOPTION_PROTOCOL_V1:
        return _fail(
            "INVALID_IDENTITY_ADOPTION_STRUCTURE",
            "identity_adoption requires adoption_protocol r06.v1",
            token=token,
            subject_id=subject_id,
        )
    missing_meta = IDENTITY_ADOPTION_REQUIRED_META_KEYS - set(meta)
    if missing_meta:
        return _fail(
            "INVALID_IDENTITY_ADOPTION_STRUCTURE",
            "identity_adoption meta is missing required reference fields",
            token=token,
            subject_id=subject_id,
        )
    proposal_event_id = _positive_int(meta.get("proposal_event_id"))
    anchor_event_id = _positive_int(meta.get("anchor_event_id"))
    ratify_event_id = _positive_int(meta.get("ratify_event_id"))
    proposal_origin_event_id = _positive_int(meta.get("proposal_origin_event_id"))
    ratify_origin_event_id = _positive_int(meta.get("ratify_origin_event_id"))
    if None in {
        proposal_event_id,
        anchor_event_id,
        ratify_event_id,
        proposal_origin_event_id,
        ratify_origin_event_id,
    }:
        return _fail(
            "INVALID_IDENTITY_ADOPTION_STRUCTURE",
            "identity_adoption reference ids must be positive integers",
            token=token,
            subject_id=subject_id,
        )
    if meta.get("anchor_kind") != "reflection":
        return _fail(
            "INVALID_ADOPTION_REFERENT_KIND",
            "identity_adoption anchor_kind must be reflection",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    ids = (proposal_event_id, anchor_event_id, ratify_event_id)
    if len(set(ids)) != 3:
        return _fail(
            "INVALID_ADOPTION_ORDER",
            "identity_adoption proposal, anchor, and ratify ids must be distinct",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if not (proposal_event_id < anchor_event_id < ratify_event_id):
        return _fail(
            "INVALID_ADOPTION_ORDER",
            "identity_adoption requires proposal < anchor < ratify",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if adoption_id is not None and not (ratify_event_id < adoption_id):
        return _fail(
            "INVALID_ADOPTION_ORDER",
            "identity_adoption referents must precede the adoption event",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )

    proposal = get_event(proposal_event_id)
    anchor = get_event(anchor_event_id)
    ratify = get_event(ratify_event_id)
    missing = [
        event_id
        for event_id, loaded in (
            (proposal_event_id, proposal),
            (anchor_event_id, anchor),
            (ratify_event_id, ratify),
        )
        if loaded is None
    ]
    if missing:
        missing_text = ",".join(str(event_id) for event_id in missing)
        return _fail(
            "MISSING_ADOPTION_REFERENT",
            f"missing identity_adoption referents: {missing_text}",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )

    parsed_proposal = parse_identity_claim_event(proposal)
    parsed_ratify = parse_identity_claim_event(ratify)
    parsed_anchor = parse_identity_anchor(anchor)
    if parsed_proposal is None or parsed_proposal["claim_type"] != "identity_proposal":
        return _fail(
            "INVALID_ADOPTION_REFERENT_KIND",
            "proposal_event_id must identify an identity_proposal claim",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if parsed_ratify is None or parsed_ratify["claim_type"] != "identity_ratify":
        return _fail(
            "INVALID_ADOPTION_REFERENT_KIND",
            "ratify_event_id must identify an identity_ratify claim",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if parsed_anchor is None:
        return _fail(
            "IDENTITY_ANCHOR_UNRELATED",
            "anchor_event_id must be a reflection with an exact v1 identity relation",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if not _identity_proposal_evidence_valid(parsed_proposal, get_event):
        return _fail(
            "INVALID_IDENTITY_EVIDENCE",
            "identity proposal evidence must identify earlier ledger events",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if parsed_proposal["token"] != token or parsed_ratify["token"] != token:
        return _fail(
            "IDENTITY_TOKEN_MISMATCH",
            "proposal, ratification, and adoption tokens must match",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if parsed_proposal["subject_id"] != subject_id or parsed_ratify["subject_id"] != subject_id:
        return _fail(
            "IDENTITY_SUBJECT_MISMATCH",
            "proposal, ratification, and adoption subject_id must match",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if (
        parsed_anchor["token"] != token
        or parsed_anchor["subject_id"] != subject_id
        or parsed_anchor["proposal_event_id"] != proposal_event_id
    ):
        return _fail(
            "IDENTITY_ANCHOR_UNRELATED",
            "anchor relation must name this proposal, subject_id, and token",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )

    proposal_origin = parsed_proposal["origin_event_id"]
    ratify_origin = parsed_ratify["origin_event_id"]
    if proposal_origin != proposal_origin_event_id or ratify_origin != ratify_origin_event_id:
        return _fail(
            "IDENTITY_ACTOR_INVALID",
            "adoption origin ids must copy the referenced identity claims",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if proposal_origin is None or ratify_origin is None:
        return _fail(
            "IDENTITY_ACTOR_INVALID",
            "identity claims must record origin_event_id",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if not _assistant_origin_valid(
        get_event(proposal_origin),
        origin_id=proposal_origin,
        before_event_id=proposal_event_id,
        claim_type="identity_proposal",
        claim_data=parsed_proposal["data"],
    ):
        return _fail(
            "IDENTITY_ACTOR_INVALID",
            "proposal origin must be the earlier assistant_message that emitted the claim",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if not _assistant_origin_valid(
        get_event(ratify_origin),
        origin_id=ratify_origin,
        before_event_id=ratify_event_id,
        claim_type="identity_ratify",
        claim_data=parsed_ratify["data"],
    ):
        return _fail(
            "IDENTITY_ACTOR_INVALID",
            "ratify origin must be the earlier assistant_message that emitted the claim",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    if not (ratify_origin > anchor_event_id):
        return _fail(
            "IDENTITY_RATIFY_ORIGIN_NOT_LATER",
            "ratification must originate in a later assistant event than the anchor",
            token=token,
            subject_id=subject_id,
            proposal_event_id=proposal_event_id,
            anchor_event_id=anchor_event_id,
            ratify_event_id=ratify_event_id,
        )
    return IdentityAdoptionValidation(
        True,
        "VALID",
        "identity adoption chain valid",
        token=token,
        subject_id=subject_id,
        proposal_event_id=proposal_event_id,
        anchor_event_id=anchor_event_id,
        ratify_event_id=ratify_event_id,
    )


def is_v1_authoritative_identity_adoption(
    event: Mapping[str, Any],
    get_event: GetEvent,
) -> bool:
    """True when a stored identity_adoption may project as v1 identity authority."""

    if event.get("kind") != "identity_adoption":
        return False
    meta = event.get("meta") or {}
    if not isinstance(meta, Mapping) or meta.get("adoption_protocol") != ADOPTION_PROTOCOL_V1:
        return False
    content = event.get("content")
    if not isinstance(content, str):
        return False
    result = validate_identity_adoption_payload(
        content,
        meta,
        get_event,
        adoption_id=_positive_int(event.get("id")),
    )
    return result.ok


def canonical_identity_adoption_content(*, token: str, subject_id: str) -> str:
    return _canonical_json(
        {
            "reason": IDENTITY_ADOPTION_REASON_V1,
            "subject_id": subject_id,
            "token": token,
        }
    )


def identity_anchor_meta(*, token: str, subject_id: str, proposal_event_id: int) -> Dict[str, Any]:
    return {
        "protocol": ADOPTION_PROTOCOL_V1,
        "relation": IDENTITY_ANCHOR_RELATION_V1,
        "subject_id": subject_id,
        "token": token,
        "proposal_event_id": proposal_event_id,
    }
