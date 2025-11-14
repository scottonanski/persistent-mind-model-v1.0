# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/learning/learning_metrics.py
"""Learning metrics aggregation from outcome observations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from pmm.learning.outcome_tracker import OutcomeObservation


def aggregate_outcomes(observations: List[OutcomeObservation]) -> Dict[str, Any]:
    """Aggregate success/failure stats per action_kind."""
    stats = defaultdict(lambda: {"success": 0, "failure": 0, "partial": 0, "total": 0})
    for obs in observations:
        kind = obs.action_kind
        result = obs.observed_result
        if result in ("success", "failure", "partial"):
            stats[kind][result] += 1
            stats[kind]["total"] += 1

    # Compute rates
    result = {}
    for kind, counts in stats.items():
        total = counts["total"]
        if total > 0:
            success_rate = counts["success"] / total
            failure_rate = counts["failure"] / total
        else:
            success_rate = failure_rate = 0.0
        result[kind] = {
            "success_count": counts["success"],
            "failure_count": counts["failure"],
            "partial_count": counts["partial"],
            "total_count": total,
            "success_rate": success_rate,
            "failure_rate": failure_rate,
        }
    return dict(result)
