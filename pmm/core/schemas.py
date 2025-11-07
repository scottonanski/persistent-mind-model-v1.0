# Path: pmm/core/schemas.py
"""Core schemas for PMM.

Defines lightweight data structures used across the runtime. Kept minimal
and implementation-agnostic to preserve determinism and clarity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import json


VALID_COMMITMENT_ORIGINS = {"user", "assistant", "autonomy_kernel"}
INTERNAL_COMMITMENT_ORIGIN = "autonomy_kernel"
INTERNAL_COMMITMENT_PREFIX = "mc_"


@dataclass
class Event:
    """Canonical event record stored in the EventLog."""

    id: Optional[int]
    ts: str
    kind: str
    content: str
    meta: Dict[str, Any] = field(default_factory=dict)
    prev_hash: Optional[str] = None
    hash: Optional[str] = None


@dataclass
class Claim:
    """Structured claim made by the model, for future validation."""

    type: str
    data: Dict[str, Any]


def generate_internal_cid(event_id: int) -> str:
    """Return canonical internal commitment id (zero-padded)."""
    if event_id < 0:
        raise ValueError("event_id must be non-negative")
    return f"{INTERNAL_COMMITMENT_PREFIX}{event_id:06d}"


def _validate_commitment_meta(kind: str, meta: Dict[str, Any]) -> None:
    origin = meta.get("origin")
    if not isinstance(origin, str) or origin not in VALID_COMMITMENT_ORIGINS:
        raise ValueError(f"{kind} events must include valid origin")

    cid = meta.get("cid")
    if not isinstance(cid, str) or not cid:
        raise ValueError(f"{kind} events must include cid string")

    is_internal = origin == INTERNAL_COMMITMENT_ORIGIN

    if is_internal and not cid.startswith(INTERNAL_COMMITMENT_PREFIX):
        raise ValueError("internal commitments must use mc_ prefix")

    goal_value = meta.get("goal")
    if is_internal:
        if not isinstance(goal_value, str) or not goal_value.strip():
            raise ValueError("internal commitments require goal text")
    elif "goal" in meta:
        raise ValueError("goal is reserved for internal commitments")


def validate_event(event: Dict[str, Any]) -> None:
    """Basic schema validation for event dictionaries."""
    kind = event.get("kind")
    meta = event.get("meta") or {}

    if kind in {"commitment_open", "commitment_close"}:
        _validate_commitment_meta(kind, meta)


def hash_payload(kind: str, meta: Dict[str, Any]) -> str:
    """Canonical hash payload string for commitment events."""
    payload: Dict[str, Any] = {"kind": kind}
    for key in ("cid", "origin"):
        if key in meta:
            payload[key] = meta[key]
    if meta.get("goal"):
        payload["goal"] = meta["goal"]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
