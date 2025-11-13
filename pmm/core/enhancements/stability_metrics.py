"""Deterministic stability metrics derived from ledger meta summaries."""

from __future__ import annotations

from typing import Dict, Iterable, List


class StabilityMetrics:
    """Compute replayable stability metrics from ledger artifacts."""

    def compute(
        self, events: Iterable[Dict], meta_summaries: Iterable[Dict]
    ) -> Dict[str, float]:
        commit_consistency = self._commitment_consistency(events)
        reflection_coherence = self._reflection_coherence(meta_summaries)
        overall = (commit_consistency + reflection_coherence) / 2.0
        return {
            "commitment_consistency": commit_consistency,
            "reflection_coherence": reflection_coherence,
            "overall_stability": overall,
        }

    def _commitment_consistency(self, events: Iterable[Dict]) -> float:
        opens = 0
        closes = 0
        for ev in events:
            kind = ev.get("kind")
            if kind == "commitment_open":
                opens += 1
            elif kind == "commitment_close":
                closes += 1
        if opens == 0:
            return 1.0
        return max(0.0, min(1.0, closes / opens))

    def _reflection_coherence(self, meta_summaries: Iterable[Dict]) -> float:
        spreads: List[int] = []
        for summary in meta_summaries:
            patterns = summary.get("patterns")
            if not isinstance(patterns, list) or not patterns:
                continue
            reflections = [int(p.get("reflection", 0)) for p in patterns]
            if len(reflections) < 2:
                continue
            spread = max(reflections) - min(reflections)
            spreads.append(spread)
        if not spreads:
            return 1.0
        span = max(spreads)
        normalized = min(1.0, span / 50.0)
        return max(0.0, 1.0 - normalized)
