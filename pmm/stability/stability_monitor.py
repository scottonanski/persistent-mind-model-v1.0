# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/stability/stability_monitor.py
"""Stability monitoring and metrics calculation.

Deterministic computation from event ledger.
"""

from __future__ import annotations

from typing import Any, Dict

from pmm.core.event_log import EventLog
from pmm.core.semantic_extractor import extract_closures, extract_commitments


def calculate_stability_metrics(log: EventLog, window: int = 100) -> Dict[str, Any]:
    """Calculate stability metrics from recent events.

    Uses bounded window for performance; deterministic.
    """
    recent = log.read_tail(max(1, int(window)))
    # Exclude prior stability_metrics events from calculation to avoid
    # feedback effects and preserve idempotency on repeated emission.
    recent = [e for e in recent if e.get("kind") != "stability_metrics"]

    # Count policy updates
    policy_changes = sum(1 for e in recent if e.get("kind") == "policy_update")

    # Count commitments and closures using structured parsing
    commits = sum(
        1 for e in recent if extract_commitments((e.get("content") or "").splitlines())
    )
    closes = sum(
        1 for e in recent if extract_closures((e.get("content") or "").splitlines())
    )

    # Reflection variance proxy: count of reflection events
    reflections = sum(1 for e in recent if e.get("kind") == "reflection")

    # Claim stability proxy: count of claim events
    claims = sum(1 for e in recent if e.get("kind") == "claim")

    # Compute rates
    total_events = len(recent)
    if total_events == 0:
        return {
            "window_size": window,
            "metrics": {
                "policy_change_rate": 0.0,
                "commitment_churn": 0.0,
                "reflection_variance": 0.0,
                "claim_stability": 1.0,
            },
            "stability_score": 1.0,
        }

    policy_change_rate = policy_changes / total_events
    commitment_churn = (commits + closes) / total_events
    reflection_variance = reflections / total_events  # Proxy
    claim_stability = max(
        0.0, 1.0 - (claims / total_events)
    )  # Higher claims lower stability

    # Composite score (deterministic formula)
    stability_score = 1.0 - policy_change_rate - (commitment_churn * 0.5)
    stability_score = max(0.0, min(1.0, stability_score))

    return {
        "window_size": window,
        "metrics": {
            "policy_change_rate": policy_change_rate,
            "commitment_churn": commitment_churn,
            "reflection_variance": reflection_variance,
            "claim_stability": claim_stability,
        },
        "stability_score": stability_score,
    }


def build_stability_metrics_event_content(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Build content dict for stability_metrics event."""
    return metrics
