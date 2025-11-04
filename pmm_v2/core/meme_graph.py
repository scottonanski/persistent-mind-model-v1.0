"""Minimal MemeGraph projection stub.

Tracks open commitment cids and basic event index; updated incrementally
via EventLog listener registration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class MemeGraph:
    def __init__(self) -> None:
        self._commit_open: Dict[str, Dict[str, Any]] = {}
        self._event_index: Dict[int, Dict[str, Any]] = {}

    # EventLog listener API
    def on_event(self, event: Dict[str, Any]) -> None:
        self._event_index[event["id"]] = event
        kind = event.get("kind")
        if kind == "commitment_open":
            cid = event.get("meta", {}).get("cid")
            if cid:
                self._commit_open[cid] = event
        elif kind == "commitment_close":
            cid = event.get("meta", {}).get("cid")
            if cid and cid in self._commit_open:
                del self._commit_open[cid]

    def open_commitment_cids(self) -> List[str]:
        return list(self._commit_open.keys())

    def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        return self._event_index.get(event_id)

