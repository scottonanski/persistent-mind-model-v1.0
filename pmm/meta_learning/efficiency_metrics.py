# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/meta_learning/efficiency_metrics.py
"""Efficiency metrics for meta-learning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pmm.core.event_log import EventLog
from pmm.core.semantic_extractor import extract_closures, extract_commitments
from pmm.meta_learning.pattern_detector import LearningPattern


@dataclass(frozen=True)
class EfficiencyMetrics:
    avg_reflection_to_policy_lag: float
    policy_update_rate: float
    commitment_resolution_rate: float


def calculate_efficiency_metrics(
    log: EventLog,
    patterns: List[LearningPattern],
    window: int = 500,
) -> EfficiencyMetrics:
    """Calculate efficiency metrics."""
    events = log.read_tail(max(1, int(window)))
    total_events = len(events)

    # Avg lag from patterns
    reflection_pattern = next(
        (p for p in patterns if p.name == "reflection_to_policy_update"), None
    )
    avg_lag = reflection_pattern.avg_lag_events if reflection_pattern else 0.0

    # Policy update rate
    policy_updates = sum(1 for e in events if e.get("kind") == "policy_update")
    policy_rate = policy_updates / total_events if total_events > 0 else 0.0

    # Commitment resolution rate (closes / (commits + closes))
    commits = sum(
        1 for e in events if extract_commitments((e.get("content") or "").splitlines())
    )
    closes = sum(
        1 for e in events if extract_closures((e.get("content") or "").splitlines())
    )
    total_commits = commits + closes
    resolution_rate = closes / total_commits if total_commits > 0 else 0.0

    return EfficiencyMetrics(
        avg_reflection_to_policy_lag=avg_lag,
        policy_update_rate=policy_rate,
        commitment_resolution_rate=resolution_rate,
    )
