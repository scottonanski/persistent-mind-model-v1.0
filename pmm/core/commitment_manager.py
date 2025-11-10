# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/commitment_manager.py
"""Core commitment manager with internal commitment utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from hashlib import sha1

from .event_log import EventLog
from .ledger_mirror import LedgerMirror
from .schemas import (
    INTERNAL_COMMITMENT_ORIGIN,
    generate_internal_cid,
    validate_event,
)


class CommitmentManager:
    """Manage commitment lifecycle operations against the EventLog."""

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog

    def open_internal(self, goal: str, reason: str = "") -> str:
        """Open an autonomy_kernel commitment; idempotent by (origin, goal)."""
        goal = (goal or "").strip()
        if not goal:
            return ""
        duplicate = self._find_open_commitment((INTERNAL_COMMITMENT_ORIGIN, goal))
        if duplicate:
            meta = duplicate.get("meta", {})
            existing_cid = meta.get("cid", "")
            return existing_cid

        cid = generate_internal_cid(self._next_event_id())
        meta: Dict[str, Any] = {
            "cid": cid,
            "origin": INTERNAL_COMMITMENT_ORIGIN,
            "goal": goal,
        }
        reason = (reason or "").strip()
        if reason:
            meta["reason"] = reason

        validate_event({"kind": "commitment_open", "meta": meta})
        self.eventlog.append(
            kind="commitment_open",
            content=f"Internal commitment opened: {goal}",
            meta=meta,
        )
        return cid

    # General (non-internal) commitments opened by assistant/user
    def open_commitment(self, text: str, *, source: str = "assistant") -> str:
        """Open a general commitment with canonical cid and schema-compliant meta.

        - cid: first 8 hex of sha1(text)
        - origin: one of VALID_COMMITMENT_ORIGINS (defaults to 'assistant')
        - text: original commitment text (for display/graph matching)
        """
        text = (text or "").strip()
        if not text:
            return ""
        cid = sha1(text.encode("utf-8")).hexdigest()[:8]
        meta: Dict[str, Any] = {
            "cid": cid,
            "origin": source,
            "source": source,
            "text": text,
        }
        validate_event({"kind": "commitment_open", "meta": meta})
        self.eventlog.append(
            kind="commitment_open",
            content=f"Commitment opened: {text}",
            meta=meta,
        )
        return cid

    def close_commitment(self, cid: str, *, source: str = "assistant") -> Optional[int]:
        """Append a commitment_close event for the provided cid if non-empty."""
        cid = (cid or "").strip()
        if not cid:
            return None
        meta: Dict[str, Any] = {"cid": cid, "origin": source, "source": source}
        validate_event({"kind": "commitment_close", "meta": meta})
        return self.eventlog.append(
            kind="commitment_close",
            content=f"Commitment closed: {cid}",
            meta=meta,
        )

    def apply_closures(
        self, cids: List[str], *, source: str = "assistant"
    ) -> List[str]:
        """Close only those commitments currently open; idempotent.

        Returns list of cids that were actually closed.
        """
        mirror = LedgerMirror(self.eventlog)
        closed: List[str] = []
        for cid in cids:
            if mirror.is_commitment_open(cid):
                self.close_commitment(cid, source=source)
                closed.append(cid)
        return closed

    def close_internal(self, cid: str, outcome: str = "") -> None:
        """Close an internal commitment if it remains open."""
        cid = (cid or "").strip()
        if not cid:
            return
        open_event = self._open_commitment_map().get(cid)
        meta = (open_event or {}).get("meta") or {}
        if meta.get("origin") != INTERNAL_COMMITMENT_ORIGIN:
            return

        close_meta: Dict[str, Any] = {
            "cid": cid,
            "origin": INTERNAL_COMMITMENT_ORIGIN,
        }
        outcome = (outcome or "").strip()
        if outcome:
            close_meta["outcome"] = outcome

        validate_event({"kind": "commitment_close", "meta": close_meta})
        self.eventlog.append(
            kind="commitment_close",
            content=f"Internal commitment closed: {cid}",
            meta=close_meta,
        )

    def get_open_commitments(
        self, origin: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return deterministic list of currently open commitments."""
        opens = list(self._open_commitment_map().values())
        if origin is not None:
            opens = [
                ev for ev in opens if (ev.get("meta") or {}).get("origin") == origin
            ]
        opens.sort(key=lambda ev: ev.get("id", 0))
        return opens

    def _open_commitment_map(self) -> Dict[str, Dict[str, Any]]:
        """Return map of open commitment events keyed by cid."""
        events = self.eventlog.read_all()
        opens: Dict[str, Dict[str, Any]] = {}
        for event in events:
            kind = event.get("kind")
            meta = event.get("meta") or {}
            cid = meta.get("cid")
            if not isinstance(cid, str) or not cid:
                continue
            if kind == "commitment_open":
                opens[cid] = event
            elif kind == "commitment_close":
                opens.pop(cid, None)
        return opens

    def _find_open_commitment(self, key: Tuple[str, str]) -> Optional[Dict[str, Any]]:
        """Locate open commitment by (origin, goal) pair."""
        origin, goal = key
        for event in self.get_open_commitments(origin=origin):
            meta = event.get("meta") or {}
            if meta.get("goal") == goal:
                return event
        return None

    def _next_event_id(self) -> int:
        """Return the next event id that will be allocated by EventLog."""
        tail = self.eventlog.read_tail(1)
        if tail:
            return int(tail[-1].get("id", 0)) + 1
        return 1
