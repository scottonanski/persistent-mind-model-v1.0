# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/mirror.py
"""Mirror projection for fast queries over EventLog.

Passive, rebuildable denormalized cache of open commitments, stale flags, and reflection counts.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .event_log import EventLog
from .rsm import RecursiveSelfModel
import json


class Mirror:
    STALE_THRESHOLD = 20

    def __init__(
        self,
        eventlog: EventLog,
        *,
        enable_rsm: bool = False,
        listen: bool = False,
        auto_rebuild: bool = True,
    ) -> None:
        self.eventlog = eventlog
        self.open_commitments: Dict[str, Dict] = {}
        self.stale_flags: Dict[str, bool] = {}
        self.reflection_counts: Dict[str, int] = {"user": 0, "autonomy_kernel": 0}
        self.last_event_id: int = 0
        self._rsm: Optional[RecursiveSelfModel] = None
        if enable_rsm:
            self._rsm = RecursiveSelfModel(eventlog=self.eventlog)
        if listen:
            self.eventlog.register_listener(self.sync)
        if auto_rebuild:
            self.rebuild()

    def rebuild(self, events: Optional[Iterable[Dict[str, Any]]] = None) -> None:
        self.open_commitments.clear()
        self.stale_flags.clear()
        self.reflection_counts = {"user": 0, "autonomy_kernel": 0}
        self.last_event_id = 0
        events_list = list(events if events is not None else self.eventlog.read_all())
        for event in events_list:
            self._process_event(event)
            self.last_event_id = event["id"]
        if self._rsm is not None:
            self._rsm.rebuild(events_list)

    def sync(self, event: Optional[Dict[str, Any]]) -> None:
        if not event:
            return
        event_id = event.get("id")
        if isinstance(event_id, int) and event_id <= self.last_event_id:
            return
        self._process_event(event)
        if self._rsm is not None:
            self._rsm.observe(event)
        if isinstance(event_id, int):
            self.last_event_id = event_id

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

    def read_recent_by_kind(self, kind: str, limit: int = 10) -> List[Dict[str, Any]]:
        tail = self.eventlog.read_tail(limit=200)
        filtered = [e for e in tail if e.get("kind") == kind]
        return filtered[-limit:]

    # --- Recursive Self-Model surface -------------------------------------------------

    def rsm_enabled(self) -> bool:
        return self._rsm is not None

    def rsm_snapshot(self) -> Dict[str, Any]:
        if self._rsm is None:
            return {}
        return self._rsm.snapshot()

    def rsm_knowledge_gaps(self) -> int:
        if self._rsm is None:
            return 0
        snapshot = self._rsm.snapshot()
        intents = snapshot.get("intents", {}) or {}
        reflections = snapshot.get("reflections", []) or []

        def _has_reflection(intent: str) -> bool:
            prefix = (intent or "")[:50]
            return any(
                isinstance(r, dict) and r.get("intent", "").startswith(prefix)
                for r in reflections
            )

        gaps = 0
        for intent, count in intents.items():
            try:
                count_int = int(count)
            except (TypeError, ValueError):
                continue
            if count_int == 1 and not _has_reflection(intent):
                gaps += 1
        return gaps

    def diff_rsm(self, event_id_a: int, event_id_b: int) -> Dict[str, Any]:
        if self._rsm is None or event_id_a == event_id_b:
            return {"tendencies_delta": {}, "gaps_added": [], "gaps_resolved": []}
        mirror_a = self._rebuild_up_to(event_id_a)
        mirror_b = self._rebuild_up_to(event_id_b)
        snap_a = mirror_a.rsm_snapshot()
        snap_b = mirror_b.rsm_snapshot()

        tendencies_a: Dict[str, int] = snap_a.get("behavioral_tendencies", {}) or {}
        tendencies_b: Dict[str, int] = snap_b.get("behavioral_tendencies", {}) or {}
        gaps_a: List[str] = snap_a.get("knowledge_gaps", []) or []
        gaps_b: List[str] = snap_b.get("knowledge_gaps", []) or []

        delta: Dict[str, int] = {}
        for key in sorted(set(tendencies_a) | set(tendencies_b)):
            change = tendencies_b.get(key, 0) - tendencies_a.get(key, 0)
            if change != 0:
                delta[key] = change

        gaps_added = sorted(set(gaps_b) - set(gaps_a))
        gaps_resolved = sorted(set(gaps_a) - set(gaps_b))

        return {
            "tendencies_delta": delta,
            "gaps_added": gaps_added,
            "gaps_resolved": gaps_resolved,
        }

    def _rebuild_up_to(self, event_id: int) -> "Mirror":
        events = self.eventlog.read_up_to(event_id)
        mirror = Mirror(
            self.eventlog,
            enable_rsm=self._rsm is not None,
            listen=False,
            auto_rebuild=False,
        )
        mirror.rebuild(events)
        return mirror

    def rebuild_fast(self) -> None:
        if self._rsm is None:
            return
        events = self.eventlog.read_all()
        start_id = 0
        snapshot: Optional[Dict[str, Any]] = None
        last_manifest = None
        for ev in reversed(events):
            if ev.get("kind") == "checkpoint_manifest":
                last_manifest = ev
                break
        if last_manifest is not None:
            try:
                data = json.loads(last_manifest.get("content") or "{}")
            except Exception:  # pragma: no cover - defensive
                data = {}
            start_id = int(data.get("up_to_id", 0))

        anchor_event = None
        for ev in reversed(events):
            if ev.get("kind") == "summary_update":
                if start_id == 0 or int(ev.get("id", 0)) <= start_id:
                    anchor_event = ev
                    break

        if anchor_event is None:
            self._rsm.rebuild(events)
            return

        meta = anchor_event.get("meta") or {}
        if isinstance(meta, dict):
            snapshot = meta.get("rsm_state")
        if isinstance(snapshot, dict):
            self._rsm.load_snapshot(snapshot)
        anchor_id = int(anchor_event.get("id", 0))
        start = max(start_id, anchor_id)
        for ev in events:
            if int(ev.get("id", 0)) > start:
                self._rsm.observe(ev)

    # --- Commitment helpers -----------------------------------------------------------

    def is_commitment_open(self, cid: str) -> bool:
        if not cid:
            return False
        return cid in self.open_commitments
