# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/meta_learning/pattern_detector.py
"""Detection of learning patterns in the event ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pmm.core.event_log import EventLog


@dataclass(frozen=True)
class LearningPattern:
    name: str
    count: int
    avg_lag_events: float


def detect_learning_patterns(log: EventLog, window: int = 500) -> List[LearningPattern]:
    """Detect learning patterns from recent events."""
    events = log.read_tail(max(1, int(window)))
    reflections = [e for e in events if e.get("kind") == "reflection"]
    policy_updates = [e for e in events if e.get("kind") == "policy_update"]

    # Pattern: reflection -> policy_update
    lags = []
    for pu in policy_updates:
        pu_id = pu["id"]
        prior_reflections = [r for r in reflections if r["id"] < pu_id]
        if prior_reflections:
            nearest_ref = max(prior_reflections, key=lambda r: r["id"])
            lag = pu_id - nearest_ref["id"]
            lags.append(lag)

    avg_lag = sum(lags) / len(lags) if lags else 0.0
    patterns = [
        LearningPattern("reflection_to_policy_update", len(lags), avg_lag),
    ]
    return patterns
