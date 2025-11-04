"""Lightweight read-through mirror utilities over EventLog.

For v2 minimal core, methods do simple filtered reads.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .event_log import EventLog


class LedgerMirror:
    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog

    def read_recent_by_kind(self, kind: str, limit: int = 10) -> List[Dict[str, Any]]:
        tail = self.eventlog.read_tail(limit=200)
        filtered = [e for e in tail if e.get("kind") == kind]
        return filtered[-limit:]

    def get_open_commitment_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        events = self.eventlog.read_all()
        opens: Dict[str, Dict[str, Any]] = {}
        for e in events:
            if e["kind"] == "commitment_open":
                cid = e.get("meta", {}).get("cid")
                if cid:
                    opens[cid] = e
            elif e["kind"] == "commitment_close":
                cid = e.get("meta", {}).get("cid")
                if cid and cid in opens:
                    del opens[cid]
        return list(opens.values())[:limit]

    def is_commitment_open(self, cid: str) -> bool:
        if not cid:
            return False
        events = self.eventlog.read_all()
        state = False
        for e in events:
            if e["kind"].startswith("commitment_"):
                ecid = e.get("meta", {}).get("cid")
                if ecid != cid:
                    continue
                if e["kind"] == "commitment_open":
                    state = True
                elif e["kind"] == "commitment_close":
                    state = False
        return state
