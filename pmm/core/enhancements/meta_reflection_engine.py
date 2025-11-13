"""Ledger-wide deterministic reflection pattern extraction."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph


class MetaReflectionEngine:
    """Produce deterministic meta-summaries across the commitment ledger."""

    WINDOW = 50

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self.graph = MemeGraph(eventlog)

    def generate(self) -> Dict[str, Any]:
        """Return deterministic meta-summary facts from the ledger."""

        events = self.eventlog.read_all()
        self.graph.rebuild(events)

        windows = self._split_windows(events)
        patterns = self._window_patterns(windows)
        graph_stats = self.graph.graph_stats()

        return {
            "patterns": patterns,
            "graph_stats": graph_stats,
            "event_count": len(events),
        }

    def _split_windows(self, events: Iterable[Dict]) -> List[List[Dict[str, Any]]]:
        slices: List[List[Dict[str, Any]]] = []
        batch: List[Dict[str, Any]] = []
        for ev in events:
            batch.append(ev)
            if len(batch) == self.WINDOW:
                slices.append(batch)
                batch = []
        if batch:
            slices.append(batch)
        return slices

    def _window_patterns(
        self, windows: Iterable[List[Dict[str, Any]]]
    ) -> List[Dict[str, int]]:
        patterns: List[Dict[str, int]] = []
        for window in windows:
            opens = sum(1 for ev in window if ev.get("kind") == "commitment_open")
            closes = sum(1 for ev in window if ev.get("kind") == "commitment_close")
            reflections = sum(1 for ev in window if ev.get("kind") == "reflection")
            patterns.append(
                {
                    "commitment_open": opens,
                    "commitment_close": closes,
                    "reflection": reflections,
                }
            )
        return patterns
