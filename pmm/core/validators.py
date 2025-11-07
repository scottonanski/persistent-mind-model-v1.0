# Path: pmm/core/validators.py
"""Structured claim validators for PMM minimal core.

No regex or heuristics; only direct checks against the ledger/mirror.
"""

from __future__ import annotations

from typing import Tuple

from .schemas import Claim
from .event_log import EventLog
from .ledger_mirror import LedgerMirror


def validate_claim(
    claim: Claim, ledger: EventLog, mirror: LedgerMirror
) -> Tuple[bool, str]:
    if claim.type == "event_existence":
        ev_id = int(claim.data.get("id", -1))
        exists = ledger.exists(ev_id)
        return exists, ("event exists" if exists else "no such event")
    if claim.type == "commitment_status":
        cid = str(claim.data.get("cid", ""))
        expected_open = bool(claim.data.get("open", True))
        is_open = mirror.is_commitment_open(cid)
        ok = is_open == expected_open
        return ok, ("commitment ok" if ok else "commitment mismatch")
    if claim.type == "reference":
        ev_id = int(claim.data.get("id", -1))
        ref = ledger.get(ev_id)
        ok = bool(ref)
        return ok, ("reference valid" if ok else "invalid reference")
    return True, "unknown claim type"
