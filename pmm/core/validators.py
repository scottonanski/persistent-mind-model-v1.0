# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/validators.py
"""Structured claim validators for PMM minimal core.

No regex or heuristics; only direct checks against the ledger/mirror.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Tuple

from .schemas import Claim
from .event_log import EventLog
from .mirror import Mirror


@dataclass(frozen=True)
class ClaimValidationResult:
    ok: bool
    code: str
    message: str


def validate_evidence_designations(
    value: Any, selected_event_ids: Iterable[int]
) -> Tuple[ClaimValidationResult, List[dict]]:
    """Validate formal evidence designations against this turn's retrieval."""

    if not isinstance(value, list):
        return (
            ClaimValidationResult(
                False,
                "INVALID_EVIDENCE_DESIGNATION_STRUCTURE",
                "evidence_designations must be a list",
            ),
            [],
        )

    canonical: List[dict] = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"event_id", "supports"}:
            return (
                ClaimValidationResult(
                    False,
                    "INVALID_EVIDENCE_DESIGNATION_STRUCTURE",
                    "each evidence designation must contain only event_id and supports",
                ),
                [],
            )
        event_id = item["event_id"]
        supports = item["supports"]
        if (
            not isinstance(event_id, int)
            or isinstance(event_id, bool)
            or event_id <= 0
        ):
            return (
                ClaimValidationResult(
                    False,
                    "INVALID_EVIDENCE_DESIGNATION_STRUCTURE",
                    "evidence designation event_id must be a positive integer",
                ),
                [],
            )
        if not isinstance(supports, str) or not supports.strip():
            return (
                ClaimValidationResult(
                    False,
                    "INVALID_EVIDENCE_DESIGNATION_STRUCTURE",
                    "evidence designation supports must be a non-empty string",
                ),
                [],
            )
        pair = (event_id, supports.strip())
        if pair in seen:
            return (
                ClaimValidationResult(
                    False,
                    "INVALID_EVIDENCE_DESIGNATION_STRUCTURE",
                    "duplicate evidence designation",
                ),
                [],
            )
        seen.add(pair)
        canonical.append({"event_id": event_id, "supports": supports.strip()})

    selected = set(selected_event_ids)
    unselected = sorted({item["event_id"] for item in canonical} - selected)
    if unselected:
        ids = ",".join(str(event_id) for event_id in unselected)
        return (
            ClaimValidationResult(
                False,
                "EVIDENCE_NOT_SELECTED",
                f"designated evidence events were not selected for this turn: {ids}",
            ),
            [],
        )
    return ClaimValidationResult(True, "VALID", "evidence designations valid"), canonical


def _validate_evidence_references(
    claim: Claim, ledger: EventLog
) -> Tuple[bool, str]:
    """Validate that any declared evidence points to existing ledger events."""

    if not isinstance(claim.data, dict) or "evidence_events" not in claim.data:
        return True, "no evidence references declared"

    evidence = claim.data["evidence_events"]
    if not isinstance(evidence, list):
        return False, "evidence_events must be a list"
    if any(
        not isinstance(event_id, int)
        or isinstance(event_id, bool)
        or event_id <= 0
        for event_id in evidence
    ):
        return False, "evidence_events must contain positive integers"

    missing = sorted(event_id for event_id in set(evidence) if not ledger.exists(event_id))
    if missing:
        missing_text = ",".join(str(event_id) for event_id in missing)
        return False, f"missing evidence events: {missing_text}"
    return True, "evidence references exist"


def _validate_identity_claim_structure(claim: Claim) -> Tuple[bool, str]:
    """Validate identity claim shape without applying adoption policy."""

    if not isinstance(claim.data, dict):
        return False, "identity payload must be an object"

    token = claim.data.get("token")
    if not isinstance(token, str) or not token.strip():
        return False, "identity token must be a non-empty string"

    if claim.type == "identity_ratify":
        unexpected = set(claim.data) - {"token"}
        if unexpected:
            return False, "identity ratification contains unsupported fields"
        return True, "identity ratification structure valid"

    allowed = {"token", "description", "evidence_events"}
    unexpected = set(claim.data) - allowed
    if unexpected:
        return False, "identity proposal contains unsupported fields"

    if "description" in claim.data:
        description = claim.data["description"]
        if not isinstance(description, str) or not description.strip():
            return False, "identity description must be a non-empty string"

    return True, "identity proposal structure valid"


def validate_claim_detailed(
    claim: Claim,
    ledger: EventLog,
    mirror: Mirror,
    selected_event_ids: Iterable[int] | None = None,
) -> ClaimValidationResult:
    evidence_ok, evidence_message = _validate_evidence_references(claim, ledger)
    if not evidence_ok:
        code = (
            "MISSING_EVIDENCE"
            if evidence_message.startswith("missing evidence events:")
            else "INVALID_EVIDENCE_STRUCTURE"
        )
        return ClaimValidationResult(False, code, evidence_message)
    if (
        selected_event_ids is not None
        and isinstance(claim.data, dict)
        and "evidence_events" in claim.data
    ):
        selected = set(selected_event_ids)
        unselected = sorted(set(claim.data["evidence_events"]) - selected)
        if unselected:
            ids = ",".join(str(event_id) for event_id in unselected)
            return ClaimValidationResult(
                False,
                "EVIDENCE_NOT_SELECTED",
                f"evidence events were not selected for this turn: {ids}",
            )
    if claim.type in {"identity_proposal", "identity_ratify"}:
        ok, message = _validate_identity_claim_structure(claim)
        return ClaimValidationResult(
            ok,
            "VALID" if ok else "INVALID_IDENTITY_STRUCTURE",
            message,
        )
    if claim.type == "event_existence":
        ev_id = int(claim.data.get("id", -1))
        exists = ledger.exists(ev_id)
        return ClaimValidationResult(
            exists,
            "VALID" if exists else "MISSING_EVENT",
            "event exists" if exists else "no such event",
        )
    if claim.type == "commitment_status":
        cid = str(claim.data.get("cid", ""))
        expected_open = bool(claim.data.get("open", True))
        is_open = mirror.is_commitment_open(cid)
        ok = is_open == expected_open
        return ClaimValidationResult(
            ok,
            "VALID" if ok else "COMMITMENT_MISMATCH",
            "commitment ok" if ok else "commitment mismatch",
        )
    if claim.type == "reference":
        ev_id = int(claim.data.get("id", -1))
        ref = ledger.get(ev_id)
        ok = bool(ref)
        return ClaimValidationResult(
            ok,
            "VALID" if ok else "INVALID_REFERENCE",
            "reference valid" if ok else "invalid reference",
        )
    return ClaimValidationResult(True, "ACCEPTED_UNKNOWN_TYPE", "unknown claim type")


def validate_claim(claim: Claim, ledger: EventLog, mirror: Mirror) -> Tuple[bool, str]:
    """Compatibility wrapper returning the original ``(ok, message)`` tuple."""

    result = validate_claim_detailed(claim, ledger, mirror)
    return result.ok, result.message
