# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/learning/policy_evolver.py
"""Policy evolution suggestions based on learning metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class PolicyChangeSuggestion:
    action_kind: str
    suggested_change: str  # "decrease_frequency", "increase_frequency", "no_change"
    reason: str


def suggest_policy_changes(
    outcome_stats: Dict[str, Any],
    failure_threshold: float = 0.7,
    success_threshold: float = 0.8,
) -> List[PolicyChangeSuggestion]:
    """Suggest policy changes based on failure/success rates."""
    suggestions = []
    for action_kind, stats in outcome_stats.items():
        failure_rate = stats.get("failure_rate", 0.0)
        success_rate = stats.get("success_rate", 0.0)
        if failure_rate >= failure_threshold:
            suggestions.append(
                PolicyChangeSuggestion(
                    action_kind=action_kind,
                    suggested_change="decrease_frequency",
                    reason=f"Failure rate {failure_rate:.2f} >= {failure_threshold}",
                )
            )
        elif success_rate >= success_threshold:
            suggestions.append(
                PolicyChangeSuggestion(
                    action_kind=action_kind,
                    suggested_change="increase_frequency",
                    reason=f"Success rate {success_rate:.2f} >= {success_threshold}",
                )
            )
        else:
            suggestions.append(
                PolicyChangeSuggestion(
                    action_kind=action_kind,
                    suggested_change="no_change",
                    reason=f"Balanced rates: success {success_rate:.2f}, failure {failure_rate:.2f}",
                )
            )
    return suggestions


def build_policy_update_content(
    suggestions: List[PolicyChangeSuggestion],
) -> Dict[str, Any]:
    """Build content dict for policy_update event."""
    changes = {}
    for sugg in suggestions:
        if sugg.suggested_change != "no_change":
            changes[sugg.action_kind] = sugg.suggested_change
    return {
        "type": "adaptive_learning",
        "changes": changes,
        "suggestions": [
            {
                "action_kind": s.action_kind,
                "suggested_change": s.suggested_change,
                "reason": s.reason,
            }
            for s in suggestions
        ],
    }
