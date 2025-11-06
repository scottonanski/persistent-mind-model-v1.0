from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, Any, Tuple, Set

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
        self._last_snapshot: Dict[str, Any] | None = None
        self._open_cids: Set[str] = set()
        self.rebuild()
        self.eventlog.register_listener(self.sync)

    def register_append_listener(self, callback) -> None:
        """Register a callback for append events."""
        self.eventlog.register_listener(callback)

    def rebuild(self) -> None:
        """Scan read_all(), compute snapshot."""
        all_events = self.eventlog.read_all()
        snapshot, open_cids = self._analyze(all_events[-1000:])  # last 1000
        self.snapshot = snapshot
        self._open_cids = open_cids
        self._maybe_emit()

    def sync(self, event: Dict[str, Any]) -> None:
        """Update counters, call _maybe_emit()."""
        kind = event.get("kind")
        if kind == "rsm_update":
            return
        self.snapshot.setdefault("intents", {})

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
                    intent_str = self._extract_user_intent(last_user)
                    ref_data = self._parse_reflection_content(event["content"])
                    next_str = ref_data.get("next", "")
                    intent_words = set(intent_str.split())
                    next_words = set(next_str.split())
                    if not intent_words <= next_words:
                        self.snapshot["gaps"] += 1
                except (json.JSONDecodeError, KeyError):
                    pass
        elif kind in ["commitment_open", "commitment_close"]:
            cid = event.get("meta", {}).get("cid")
            if kind == "commitment_open":
                if cid:
                    self._open_cids.add(cid)
            else:
                if cid:
                    self._open_cids.discard(cid)
            self.snapshot["commitments"] = len(self._open_cids)
        elif kind == "user_message":
            try:
                intent_str = self._extract_user_intent(event)
                normalized = self._normalize_intent(intent_str)
                if normalized:
                    self.snapshot["intents"][normalized] = (
                        self.snapshot["intents"].get(normalized, 0) + 1
                    )
            except (json.JSONDecodeError, KeyError):
                pass
        # Gaps not updated incrementally for simplicity
        self._maybe_emit()

    def get_snapshot(self) -> Dict[str, Any]:
        """Return dict."""
        return self.snapshot.copy()

    def _analyze(self, tail: list[Dict[str, Any]]) -> Tuple[Dict[str, Any], Set[str]]:
        """Parse last 1000 events."""
        reflections = sum(1 for e in tail if e.get("kind") == "reflection")
        open_cids: Set[str] = set()
        intents = defaultdict(int)
        gaps = 0

        # Collect intents
        for e in tail:
            if e.get("kind") == "user_message":
                try:
                    intent_str = self._extract_user_intent(e)
                    normalized = self._normalize_intent(intent_str)
                    if normalized:
                        intents[normalized] += 1
                except (json.JSONDecodeError, KeyError):
                    pass
            elif e.get("kind") == "commitment_open":
                cid = e.get("meta", {}).get("cid")
                if cid:
                    open_cids.add(cid)
            elif e.get("kind") == "commitment_close":
                cid = e.get("meta", {}).get("cid")
                if cid:
                    open_cids.discard(cid)

        # Compute gaps for last 500 events
        recent_tail = tail[-500:]
        for i in range(len(recent_tail)):
            if recent_tail[i].get("kind") == "user_message":
                intent_str = ""
                try:
                    intent_str = self._extract_user_intent(recent_tail[i])
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
                        ref_data = self._parse_reflection_content(next_ref["content"])
                        next_str = ref_data.get("next", "")
                        intent_words = set(intent_str.split())
                        next_words = set(next_str.split())
                        if not intent_words <= next_words:
                            gaps += 1
                    except (json.JSONDecodeError, KeyError):
                        pass

        snapshot = {
            "reflections": reflections,
            "commitments": len(open_cids),
            "intents": dict(intents),
            "gaps": gaps,
        }
        return snapshot, set(open_cids)

    def _maybe_emit(self) -> None:
        """If delta > 0.05 vs last_rsm_update → append 'rsm_update'."""
        current_score = self.snapshot["gaps"] / (self.snapshot["reflections"] + 1)
        prev_score = self.last_score
        prev_snapshot = self._last_snapshot or {}
        significant_score_delta = (
            prev_score is None or abs(current_score - prev_score) > 0.05
        )
        counts_changed = any(
            self.snapshot.get(key) != prev_snapshot.get(key)
            for key in ("reflections", "commitments", "gaps")
        )
        intents_changed = self.snapshot.get("intents", {}) != prev_snapshot.get(
            "intents", {}
        )
        if significant_score_delta or counts_changed or intents_changed:
            content = json.dumps(self.snapshot, sort_keys=True, separators=(",", ":"))
            self.eventlog.append(kind="rsm_update", content=content, meta={})
        self.last_score = current_score
        self._last_snapshot = self.snapshot.copy()

    def _parse_reflection_content(self, content: str) -> Dict[str, str]:
        """Support both legacy string and JSON reflection payloads."""
        content = (content or "").strip()
        if not content:
            return {}
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        return {}

    def _extract_user_intent(self, event: Dict[str, Any]) -> str:
        """Return intent text from user_message content."""
        content = event.get("content", "")
        try:
            data = json.loads(content)
            intent = data.get("intent", "")
            if isinstance(intent, str):
                return intent.strip()
        except (json.JSONDecodeError, AttributeError):
            pass
        return content.strip()

    def _normalize_intent(self, text: str) -> str:
        """Normalize free-text intent into a bounded string key."""
        text = (text or "").strip()
        if not text:
            return ""
        if len(text) > 256:
            return text[:253] + "..."
        return text
