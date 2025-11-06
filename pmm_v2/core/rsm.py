from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, Any

from pmm_v2.core.event_log import EventLog


class RecursiveSelfModel:
    HARD_CODED_INTENTS = [
        "create",
        "update",
        "delete",
        "read",
        "commit",
        "reflect",
        "monitor",
        "maintain",
        "continue",
    ]

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self.snapshot: Dict[str, Any] = {}
        self.last_score: float | None = None
        self.rebuild()
        self.eventlog.register_listener(self.sync)

    def register_append_listener(self, callback) -> None:
        """Register a callback for append events."""
        self.eventlog.register_listener(callback)

    def rebuild(self) -> None:
        """Scan read_all(), compute snapshot."""
        all_events = self.eventlog.read_all()
        self.snapshot = self._analyze(all_events[-1000:])  # last 1000
        self._maybe_emit()  # Emit on first rebuild

    def sync(self, event: Dict[str, Any]) -> None:
        """Update counters, call _maybe_emit()."""
        kind = event.get("kind")
        if kind == "reflection":
            self.snapshot["reflections"] += 1
            # Update gaps
            events = (
                self.eventlog.read_tail(10)
                if hasattr(self.eventlog, "read_tail")
                else self.eventlog.read_all()[-10:]
            )  # check last 10 for previous user
            user_msgs = [
                e for e in events[:-1] if e["kind"] == "user_message"
            ]  # exclude current
            if user_msgs:
                last_user = user_msgs[-1]
                try:
                    user_data = json.loads(last_user["content"])
                    intent_str = user_data.get("intent", "")
                    ref_data = json.loads(event["content"])
                    next_str = ref_data.get("next", "")
                    intent_words = set(intent_str.split())
                    next_words = set(next_str.split())
                    if not intent_words <= next_words:
                        self.snapshot["gaps"] += 1
                except (json.JSONDecodeError, KeyError):
                    pass
        elif kind in ["commitment_open", "commitment_close"]:
            self.snapshot["commitments"] += 1
        elif kind == "user_message":
            try:
                data = json.loads(event["content"])
                intent_str = data.get("intent", "")
                words = intent_str.split()
                for word in words:
                    if word in self.HARD_CODED_INTENTS:
                        self.snapshot["intents"][word] = (
                            self.snapshot["intents"].get(word, 0) + 1
                        )
            except (json.JSONDecodeError, KeyError):
                pass
        # Gaps not updated incrementally for simplicity
        self._maybe_emit()

    def get_snapshot(self) -> Dict[str, Any]:
        """Return dict."""
        return self.snapshot.copy()

    def _analyze(self, tail: list[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse last 1000 events."""
        reflections = sum(1 for e in tail if e.get("kind") == "reflection")
        commitments = sum(
            1 for e in tail if e.get("kind") in ["commitment_open", "commitment_close"]
        )
        intents = defaultdict(int)
        gaps = 0

        # Collect intents
        for e in tail:
            if e.get("kind") == "user_message":
                try:
                    data = json.loads(e["content"])
                    intent_str = data.get("intent", "")
                    words = intent_str.split()
                    for word in words:
                        if word in self.HARD_CODED_INTENTS:
                            intents[word] += 1
                except (json.JSONDecodeError, KeyError):
                    pass

        # Compute gaps for last 500 events
        recent_tail = tail[-500:]
        for i in range(len(recent_tail)):
            if recent_tail[i].get("kind") == "user_message":
                intent_str = ""
                try:
                    data = json.loads(recent_tail[i]["content"])
                    intent_str = data.get("intent", "")
                except (json.JSONDecodeError, KeyError):
                    pass
                # Find next reflection
                next_ref = None
                for j in range(i + 1, len(recent_tail)):
                    if recent_tail[j].get("kind") == "reflection":
                        next_ref = recent_tail[j]
                        break
                if next_ref:
                    try:
                        ref_data = json.loads(next_ref["content"])
                        next_str = ref_data.get("next", "")
                        intent_words = set(intent_str.split())
                        next_words = set(next_str.split())
                        if not intent_words <= next_words:
                            gaps += 1
                    except (json.JSONDecodeError, KeyError):
                        pass

        return {
            "reflections": reflections,
            "commitments": commitments,
            "intents": dict(intents),
            "gaps": gaps,
        }

    def _maybe_emit(self) -> None:
        """If delta > 0.05 vs last_rsm_update → append 'rsm_update'."""
        current_score = self.snapshot["gaps"] / (self.snapshot["reflections"] + 1)
        if self.last_score is None or abs(current_score - self.last_score) > 0.05:
            content = json.dumps(self.snapshot, sort_keys=True, separators=(",", ":"))
            self.eventlog.append(kind="rsm_update", content=content, meta={})
            self.last_score = current_score
