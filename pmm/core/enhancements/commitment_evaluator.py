"""Deterministic commitment impact scoring built atop existing projections."""

from __future__ import annotations

from typing import Dict, Iterable, List

from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph


class CommitmentEvaluator:
    """Pure ledger-derived commitment impact scorer."""

    DEFAULT_SUCCESS_PRIOR = 0.5

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self.graph = MemeGraph(eventlog)

    def compute_impact_score(self, text: str) -> float:
        """Return a bounded impact score in [0, 1] for the provided text."""

        candidate = (text or "").strip()
        if not candidate:
            return 0.0

        events = self.eventlog.read_all()
        self.graph.rebuild(events)

        hist = self._historical_success(events, candidate)
        weight = self._graph_weight()

        score = hist * weight
        return max(0.0, min(1.0, score))

    def _historical_success(self, events: Iterable[Dict], text: str) -> float:
        """Deterministically estimate success rate for matching commitment text."""

        total = 0
        closes = 0
        tracked_cids: List[str] = []
        for ev in events:
            kind = ev.get("kind")
            if kind == "commitment_open":
                meta = ev.get("meta") or {}
                if meta.get("text") == text:
                    total += 1
                    cid = meta.get("cid")
                    if isinstance(cid, str) and cid:
                        tracked_cids.append(cid)
            elif kind == "commitment_close":
                meta = ev.get("meta") or {}
                cid = meta.get("cid")
                if isinstance(cid, str) and cid in tracked_cids:
                    closes += 1

        if total == 0:
            return self.DEFAULT_SUCCESS_PRIOR
        return min(1.0, closes / total)

    def _graph_weight(self) -> float:
        """Return a graph-derived weight favouring denser commitment threads."""

        stats = self.graph.graph_stats()
        nodes = int(stats.get("nodes", 1))
        edges = int(stats.get("edges", 0))
        if nodes <= 0 or edges < 0:
            return 1.0
        if edges == 0:
            return 1.0
        if edges <= 1:
            return 1.0
        weight = nodes / (nodes + edges) if (nodes + edges) > 0 else 1.0
        return max(0.0, min(1.0, weight))
