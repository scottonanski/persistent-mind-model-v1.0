# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/mirror.py
"""Mirror projection for fast queries over EventLog.

Passive, rebuildable denormalized cache of open commitments, stale flags, and reflection counts.
"""

from __future__ import annotations

from typing import Dict, List

from .event_log import EventLog


class Mirror:
    STALE_THRESHOLD = 20

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self.open_commitments: Dict[str, Dict] = {}
        self.stale_flags: Dict[str, bool] = {}
        self.reflection_counts: Dict[str, int] = {"user": 0, "autonomy_kernel": 0}
        self.last_event_id: int = 0
        self.rebuild()

    def rebuild(self) -> None:
        self.open_commitments.clear()
        self.stale_flags.clear()
        self.reflection_counts = {"user": 0, "autonomy_kernel": 0}
        self.last_event_id = 0
        for event in self.eventlog.read_all():
            self._process_event(event)
            self.last_event_id = event["id"]

    def sync(self, event: Dict) -> None:
        if event["id"] <= self.last_event_id:
            return
        self._process_event(event)
        self.last_event_id = event["id"]

    def _process_event(self, event: Dict) -> None:
        kind = event.get("kind")
        meta = event.get("meta", {})
        if kind == "commitment_open":
            # Canonical: require meta.cid for opens
            cid = meta.get("cid")
            if isinstance(cid, str) and cid:
                source = meta.get("source", "user")
                self.open_commitments[cid] = {"event_id": event["id"], "source": source}
                self.stale_flags[cid] = False
        elif kind == "commitment_close":
            # Canonical: close strictly by meta.cid
            cid = meta.get("cid")
            if isinstance(cid, str) and cid:
                if cid in self.open_commitments:
                    del self.open_commitments[cid]
                if cid in self.stale_flags:
                    del self.stale_flags[cid]
        elif kind == "reflection":
            source = meta.get("source", "user")
            if source not in self.reflection_counts:
                self.reflection_counts[source] = 0
            self.reflection_counts[source] += 1
        # Update stale flags
        current_id = event["id"]
        for cid, data in list(self.open_commitments.items()):
            if current_id - data["event_id"] > self.STALE_THRESHOLD:
                self.stale_flags[cid] = True

    def get_open_commitment_events(self) -> List[Dict]:
        return [
            self.eventlog.get(data["event_id"])
            for data in self.open_commitments.values()
        ]
