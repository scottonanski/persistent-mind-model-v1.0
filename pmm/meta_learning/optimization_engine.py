# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/meta_learning/optimization_engine.py
"""Meta-policy optimization suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from pmm.meta_learning.efficiency_metrics import EfficiencyMetrics


@dataclass(frozen=True)
class MetaPolicySuggestion:
    param: str
    suggested_change: str  # "increase", "decrease", "no_change"
    reason: str


def suggest_meta_policy_changes(
    efficiency: EfficiencyMetrics,
    stability_score: Optional[float] = None,
) -> List[MetaPolicySuggestion]:
    """Suggest meta-policy changes."""
    suggestions = []

    # Rule 1: High lag and good stability -> more frequent reflections
    if efficiency.avg_reflection_to_policy_lag > 50 and (
        stability_score is None or stability_score > 0.7
    ):
        suggestions.append(
            MetaPolicySuggestion(
                param="reflection_interval",
                suggested_change="decrease",
                reason=f"High lag {efficiency.avg_reflection_to_policy_lag:.1f} with good stability",
            )
        )
    # Rule 2: High policy rate and low stability -> less frequent
    elif (
        efficiency.policy_update_rate > 0.1
        and stability_score is not None
        and stability_score < 0.5
    ):
        suggestions.append(
            MetaPolicySuggestion(
                param="reflection_interval",
                suggested_change="increase",
                reason=f"High policy rate {efficiency.policy_update_rate:.2f} with low stability",
            )
        )
    else:
        suggestions.append(
            MetaPolicySuggestion(
                param="reflection_interval",
                suggested_change="no_change",
                reason="Balanced efficiency and stability",
            )
        )

    return suggestions


def build_meta_policy_update_content(suggestions: List[MetaPolicySuggestion]) -> dict:
    """Build content for meta_policy_update event."""
    changes = {}
    for sugg in suggestions:
        if sugg.suggested_change != "no_change":
            changes[sugg.param] = sugg.suggested_change
    return {
        "type": "meta_learning",
        "changes": changes,
        "suggestions": [
            {
                "param": s.param,
                "suggested_change": s.suggested_change,
                "reason": s.reason,
            }
            for s in suggestions
        ],
    }
