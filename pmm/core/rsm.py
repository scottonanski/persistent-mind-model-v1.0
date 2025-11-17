# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Deterministic Recursive Self-Model utilities built from ledger events."""

from __future__ import annotations

from collections import defaultdict, deque
import json
from typing import Any, Deque, Dict, Iterable, List, Optional, Tuple

from .event_log import EventLog
from .concept_metrics import compute_concept_metrics


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
        # Concept-level metrics are derived deterministically from the ledger.
        concept_metrics: Dict[str, Any] = {}
        if self.eventlog is not None:
            try:
                concept_metrics = compute_concept_metrics(self.eventlog)
            except Exception:
                # RSM snapshot must remain robust even if CTL is unused or misconfigured.
                concept_metrics = {}
        return {
            "behavioral_tendencies": dict(self.behavioral_tendencies),
            "knowledge_gaps": list(self.knowledge_gaps),
            "interaction_meta_patterns": list(self.interaction_meta_patterns),
            "intents": dict(self._gap_counts),
            "reflections": [{"intent": i} for i in self.reflection_intents],
            "concept_metrics": concept_metrics,
        }

    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Seed internal state from an existing snapshot."""
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
        refl = snapshot.get("reflections") or []
        if isinstance(refl, list):
            for item in refl:
                if isinstance(item, dict) and isinstance(item.get("intent"), str):
                    self.reflection_intents.append(item["intent"])
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
        total = 0
        for marker in markers:
            total += content_lower.count(marker)
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
