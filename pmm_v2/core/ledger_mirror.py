"""Lightweight read-through mirror utilities over EventLog with RSM support."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

from .event_log import EventLog


class RecursiveSelfModel:
    """Deterministic, replay-safe snapshot built from ledger events only."""

    _KNOWLEDGE_WINDOW = 500
    _IDENTITY_QUERY_MARKERS = ("who are you",)
    _DETERMINISM_MARKERS = ("determinism", "deterministic")
    _BEHAVIORAL_PATTERNS: Dict[str, Tuple[Optional[Iterable[str]], Tuple[str, ...]]] = {
        "identity_query": (("user_message",), _IDENTITY_QUERY_MARKERS),
        "determinism_emphasis": (
            ("assistant_message", "reflection"),
            _DETERMINISM_MARKERS,
        ),
    }
    _IDENTITY_FOLLOWUP_LIMIT = 5
    _META_PATTERN_LABEL = "identity_queries_trigger_determinism_ref"

    def __init__(self) -> None:
        self._event_index = 0
        self._last_processed_event_id: Optional[int] = None
        self._pattern_counts: Dict[str, int] = defaultdict(int)
        self._gap_counts: Dict[str, int] = defaultdict(int)
        self._gap_window: Deque[Tuple[int, str]] = deque()
        self._meta_patterns: set[str] = set()
        self._last_identity_event: Optional[int] = None
        self.behavioral_tendencies: Dict[str, int] = {}
        self.knowledge_gaps: List[str] = []
        self.interaction_meta_patterns: List[str] = []

    def reset(self) -> None:
        self._event_index = 0
        self._last_processed_event_id = None
        self._pattern_counts.clear()
        self._gap_counts.clear()
        self._gap_window.clear()
        self._meta_patterns.clear()
        self._last_identity_event = None
        self.behavioral_tendencies = {}
        self.knowledge_gaps = []
        self.interaction_meta_patterns = []

    def rebuild(self, events: Iterable[Dict[str, Any]]) -> None:
        """Rebuild internal state from the supplied ordered events."""
        self.reset()
        for event in events:
            self.observe(event)

    def observe(self, event: Optional[Dict[str, Any]]) -> None:
        """Process a single event incrementally."""
        if not event:
            return
        kind = event.get("kind")
        if kind == "rsm_update":
            return
        event_id = event.get("id")
        if isinstance(event_id, int):
            if (
                self._last_processed_event_id is not None
                and event_id <= self._last_processed_event_id
            ):
                return
            self._last_processed_event_id = event_id

        self._event_index += 1
        event_idx = self._event_index
        content = (event.get("content") or "").strip()
        content_lower = content.lower()
        meta = event.get("meta") or {}

        self._track_behavioral_patterns(kind, content_lower)
        self._track_meta_patterns(kind, content_lower, event_idx)
        self._track_knowledge_gaps(kind, content_lower, meta, event_idx)
        self._trim_gap_window()

        # Produce deterministic outward-facing structures
        self.behavioral_tendencies = dict(sorted(self._pattern_counts.items()))
        self.knowledge_gaps = sorted(
            topic for topic, count in self._gap_counts.items() if count > 3
        )
        self.interaction_meta_patterns = sorted(self._meta_patterns)

    def snapshot(self) -> Dict[str, Any]:
        """Return serialized snapshot for reflections or diagnostics."""
        return {
            "behavioral_tendencies": dict(self.behavioral_tendencies),
            "knowledge_gaps": list(self.knowledge_gaps),
            "interaction_meta_patterns": list(self.interaction_meta_patterns),
        }

    def knowledge_gap_count(self) -> int:
        return len(self.knowledge_gaps)

    def _track_behavioral_patterns(
        self, kind: Optional[str], content_lower: str
    ) -> None:
        if not content_lower:
            return
        for pattern, (kinds, markers) in self._BEHAVIORAL_PATTERNS.items():
            if kinds and kind not in kinds:
                continue
            for marker in markers:
                if marker in content_lower:
                    self._pattern_counts[pattern] += 1
                    if pattern == "identity_query":
                        self._last_identity_event = self._event_index
                    break

    def _track_meta_patterns(
        self, kind: Optional[str], content_lower: str, event_idx: int
    ) -> None:
        if (
            kind == "reflection"
            and self._last_identity_event
            and event_idx - self._last_identity_event <= self._IDENTITY_FOLLOWUP_LIMIT
        ):
            for marker in self._DETERMINISM_MARKERS:
                if marker in content_lower:
                    self._meta_patterns.add(self._META_PATTERN_LABEL)
                    break

    def _track_knowledge_gaps(
        self,
        kind: Optional[str],
        content_lower: str,
        meta: Dict[str, Any],
        event_idx: int,
    ) -> None:
        if kind != "assistant_message":
            return
        if "claim: failed" not in content_lower and "unknown" not in content_lower:
            return

        topic = meta.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            topic = "general"
        topic = topic.strip()

        self._gap_window.append((event_idx, topic))
        self._gap_counts[topic] += 1

    def _trim_gap_window(self) -> None:
        if not self._gap_window:
            return
        min_allowed = max(1, self._event_index - self._KNOWLEDGE_WINDOW + 1)
        while self._gap_window and self._gap_window[0][0] < min_allowed:
            _, old_topic = self._gap_window.popleft()
            self._gap_counts[old_topic] -= 1
            if self._gap_counts[old_topic] <= 0:
                del self._gap_counts[old_topic]


class LedgerMirror:
    def __init__(self, eventlog: EventLog, *, listen: bool = True) -> None:
        self.eventlog = eventlog
        self._rsm = RecursiveSelfModel()
        self._rsm.rebuild(self.eventlog.read_all())
        if listen:
            self.eventlog.register_listener(self.sync)

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

    def sync(self, event: Optional[Dict[str, Any]]) -> None:
        """Incrementally update the RecursiveSelfModel from a new event."""
        self._rsm.observe(event)

    def rsm_snapshot(self) -> Dict[str, Any]:
        return self._rsm.snapshot()

    def rsm_knowledge_gaps(self) -> int:
        return self._rsm.knowledge_gap_count()

    def diff_rsm(self, event_id_a: int, event_id_b: int) -> Dict[str, Any]:
        base = {
            "tendencies_delta": {},
            "gaps_added": [],
            "gaps_resolved": [],
        }
        if event_id_a == event_id_b:
            return base

        mirror_a = self._rebuild_up_to(event_id_a)
        mirror_b = self._rebuild_up_to(event_id_b)

        snapshot_a = mirror_a.rsm_snapshot()
        snapshot_b = mirror_b.rsm_snapshot()

        tendencies_a: Dict[str, int] = snapshot_a.get("behavioral_tendencies", {}) or {}
        tendencies_b: Dict[str, int] = snapshot_b.get("behavioral_tendencies", {}) or {}
        gaps_a: List[str] = snapshot_a.get("knowledge_gaps", []) or []
        gaps_b: List[str] = snapshot_b.get("knowledge_gaps", []) or []

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

    def _rebuild_up_to(self, event_id: int) -> LedgerMirror:
        events = self.eventlog.read_up_to(event_id)
        mirror = object.__new__(LedgerMirror)
        mirror.eventlog = self.eventlog
        mirror._rsm = RecursiveSelfModel()
        mirror._rsm.rebuild(events)
        return mirror
