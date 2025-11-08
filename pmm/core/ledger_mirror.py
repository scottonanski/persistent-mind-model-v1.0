# Path: pmm/core/ledger_mirror.py
"""Lightweight read-through mirror utilities over EventLog with RSM support."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple
import json

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
        # Sprint 21: Track stability/adaptability emphasis deterministically
        "stability_emphasis": (
            ("assistant_message", "reflection"),
            ("stability",),
        ),
        "adaptability_emphasis": (
            ("assistant_message", "reflection"),
            ("adaptability", "adapt"),
        ),
        "instantiation_capacity": (
            ("assistant_message", "reflection"),
            ("instantiation", "entity"),
        ),
    }
    _IDENTITY_FOLLOWUP_LIMIT = 5
    _META_PATTERN_LABEL = "identity_queries_trigger_determinism_ref"

    def __init__(self, eventlog: Optional[EventLog] = None) -> None:
        self.eventlog = eventlog
        self._event_index = 0
        self._last_processed_event_id: Optional[int] = None
        self._pattern_counts: Dict[str, int] = defaultdict(int)
        self._gap_counts: Dict[str, int] = defaultdict(int)
        self._gap_window: Deque[Tuple[int, str]] = deque()
        self._meta_patterns: set[str] = set()
        self._last_identity_event: Optional[int] = None
        # Uniqueness tracking (first 8 chars of event hash)
        self._unique_prefixes: set[str] = set()
        self._total_events: int = 0
        self.behavioral_tendencies: Dict[str, int] = {}
        self.knowledge_gaps: List[str] = []
        self.interaction_meta_patterns: List[str] = []
        self.reflection_intents: List[str] = []

    def reset(self) -> None:
        self._event_index = 0
        self._last_processed_event_id = None
        self._pattern_counts.clear()
        self._gap_counts.clear()
        self._gap_window.clear()
        self._meta_patterns.clear()
        self._last_identity_event = None
        self._unique_prefixes.clear()
        self._total_events = 0
        self.behavioral_tendencies = {}
        self.knowledge_gaps = []
        self.interaction_meta_patterns = []
        self.reflection_intents = []

    def rebuild(self, events: Iterable[Dict[str, Any]]) -> None:
        """Rebuild internal state from the supplied ordered events."""
        self.reset()
        for event in events:
            self.observe(event)
        # After full rebuild, ensure uniqueness cache reflects all events.
        # If an eventlog is available, read from it for complete coverage.
        if self.eventlog is not None:
            try:
                all_events = self.eventlog.read_all()
                self._unique_prefixes = {
                    (e.get("hash") or "")[:8] for e in all_events if e.get("hash")
                }
                self._total_events = len(all_events)
            except Exception:
                # Fallback is already populated via observe loop
                pass

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
        # Track uniqueness from event hash prefix
        ev_hash = event.get("hash") or ""
        if ev_hash:
            self._unique_prefixes.add(ev_hash[:8])
        self._total_events += 1

        self._track_behavioral_patterns(kind, content_lower)
        self._track_meta_patterns(kind, content_lower, event_idx)
        self._track_knowledge_gaps(kind, content_lower, meta, event_idx)
        self._trim_gap_window()

        if kind == "reflection":
            try:
                data = json.loads(content)
            except ValueError:
                data = {}
            intent = data.get("intent") if isinstance(data, dict) else None
            if isinstance(intent, str):
                self.reflection_intents.append(intent)

        # Cap behavioral counters for bounded runtime while preserving determinism
        for key in list(self._pattern_counts.keys()):
            if self._pattern_counts[key] > 50:
                self._pattern_counts[key] = 50

        # Compute uniqueness emphasis (0..20, typical 0..10)
        uniq_score = int((len(self._unique_prefixes) / max(1, self._total_events)) * 10)
        if uniq_score > 20:
            uniq_score = 20
        self._pattern_counts["uniqueness_emphasis"] = uniq_score

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
            "intents": dict(self._gap_counts),
            "reflections": [{"intent": i} for i in self.reflection_intents],
        }

    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Seed internal state from an existing snapshot.

        Deterministic: used only as a checkpoint to reduce replay work. The
        snapshot should originate from `snapshot()` content (e.g., in
        summary_update.meta.rsm_state). Fields not present are treated as empty.
        """
        self.reset()
        tendencies = snapshot.get("behavioral_tendencies") or {}
        if isinstance(tendencies, dict):
            for k, v in tendencies.items():
                try:
                    self._pattern_counts[str(k)] = int(v)
                except Exception:
                    continue
        gaps = snapshot.get("knowledge_gaps") or []
        if isinstance(gaps, list):
            for g in gaps:
                self._gap_counts[str(g)] = max(1, self._gap_counts.get(str(g), 0) + 1)
        imeta = snapshot.get("interaction_meta_patterns") or []
        if isinstance(imeta, list):
            self._meta_patterns = set(str(x) for x in imeta)
        # Export outward facing structures
        self.behavioral_tendencies = dict(sorted(self._pattern_counts.items()))
        self.knowledge_gaps = sorted(k for k in self._gap_counts.keys())
        self.interaction_meta_patterns = sorted(self._meta_patterns)

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
            inc = self._count_markers(content_lower, markers)
            if inc > 0:
                self._pattern_counts[pattern] += inc
                if pattern == "identity_query":
                    self._last_identity_event = self._event_index

    @staticmethod
    def _count_markers(content_lower: str, markers: Iterable[str]) -> int:
        """Sum case-insensitive marker occurrences deterministically.

        `content_lower` must already be lowercased. For each marker, count
        non-overlapping occurrences using `str.count` and sum them.
        """
        total = 0
        for m in markers:
            # markers are simple substrings; the content is lower-cased above
            total += content_lower.count(m)
        return total

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
        self._rsm = RecursiveSelfModel(eventlog=self.eventlog)
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
        snapshot = self.rsm_snapshot()
        gaps = 0
        for intent, count in snapshot["intents"].items():
            if count == 1:  # singleton
                # Check if ANY reflection covers it (first 50 chars)
                if not any(
                    r["intent"].startswith(intent[:50]) for r in snapshot["reflections"]
                ):
                    gaps += 1
        return gaps

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
        mirror._rsm = RecursiveSelfModel(eventlog=self.eventlog)
        mirror._rsm.rebuild(events)
        return mirror

    # Fast rebuild using last summary_update snapshot if available
    def rebuild_fast(self) -> None:
        events = self.eventlog.read_all()
        # Prefer checkpoint_manifest if available; otherwise fall back to last summary_update
        start_id = 0
        snap = None
        # Find last checkpoint_manifest
        last_manifest = None
        for ev in reversed(events):
            if ev.get("kind") == "checkpoint_manifest":
                last_manifest = ev
                break
        if last_manifest is not None:
            try:
                data = json.loads(last_manifest.get("content") or "{}")
            except Exception:
                data = {}
            start_id = int(data.get("up_to_id", 0))
        # Find last summary_update at or before start_id (or the absolute last if no manifest)
        last_summary = None
        for ev in reversed(events):
            if ev.get("kind") == "summary_update":
                if start_id == 0 or int(ev.get("id", 0)) <= start_id:
                    last_summary = ev
                    break
        if last_summary is None:
            # Fallback to full rebuild
            self._rsm.rebuild(events)
            return
        meta = last_summary.get("meta") or {}
        if isinstance(meta, dict):
            snap = meta.get("rsm_state")
        if isinstance(snap, dict):
            self._rsm.load_snapshot(snap)
        anchor = int(last_summary.get("id", 0))
        # Replay only subsequent events after the stronger of manifest or summary anchor
        start = max(start_id, anchor)
        for ev in events:
            if int(ev.get("id", 0)) > start:
                self._rsm.observe(ev)
