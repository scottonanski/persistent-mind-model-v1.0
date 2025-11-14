# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_learning_subsystem.py
"""Tests for learning subsystem."""

import json

from pmm.core.event_log import EventLog
from pmm.learning.learning_metrics import aggregate_outcomes
from pmm.learning.outcome_tracker import (
    OutcomeObservation,
    build_outcome_observation_content,
    extract_outcome_observations,
)
from pmm.learning.policy_evolver import (
    PolicyChangeSuggestion,
    build_policy_update_content,
    suggest_policy_changes,
)


def test_extract_outcome_observations():
    """Test extraction of outcome observations."""
    log = EventLog(":memory:")
    content = build_outcome_observation_content(
        commitment_id="c1",
        action_kind="reflect",
        action_payload="data",
        observed_result="success",
        evidence_event_ids=[1, 2],
    )
    log.append(kind="outcome_observation", content=json.dumps(content))
    log.append(kind="test_event", content="{}")  # Ignored

    observations = extract_outcome_observations(log)
    assert len(observations) == 1
    obs = observations[0]
    assert obs.commitment_id == "c1"
    assert obs.action_kind == "reflect"
    assert obs.observed_result == "success"
    assert obs.evidence_event_ids == (1, 2)


def test_aggregate_outcomes():
    """Test outcome aggregation."""
    observations = [
        OutcomeObservation(1, "c1", "reflect", "p1", "success", ()),
        OutcomeObservation(2, "c2", "reflect", "p2", "failure", ()),
        OutcomeObservation(3, "c3", "summarize", "p3", "success", ()),
    ]

    stats = aggregate_outcomes(observations)
    assert stats["reflect"]["success_count"] == 1
    assert stats["reflect"]["failure_count"] == 1
    assert stats["reflect"]["success_rate"] == 0.5
    assert stats["summarize"]["success_rate"] == 1.0


def test_suggest_policy_changes():
    """Test policy suggestions."""
    stats = {
        "reflect": {"failure_rate": 0.8, "success_rate": 0.2},
        "summarize": {"failure_rate": 0.1, "success_rate": 0.9},
        "idle": {"failure_rate": 0.5, "success_rate": 0.5},
    }

    suggestions = suggest_policy_changes(
        stats, failure_threshold=0.7, success_threshold=0.8
    )
    expected = [
        PolicyChangeSuggestion(
            "reflect", "decrease_frequency", "Failure rate 0.80 >= 0.7"
        ),
        PolicyChangeSuggestion(
            "summarize", "increase_frequency", "Success rate 0.90 >= 0.8"
        ),
        PolicyChangeSuggestion(
            "idle", "no_change", "Balanced rates: success 0.50, failure 0.50"
        ),
    ]
    assert suggestions == expected


def test_build_policy_update_content():
    """Test building policy update content."""
    suggestions = [
        PolicyChangeSuggestion("reflect", "decrease_frequency", "high failure"),
        PolicyChangeSuggestion("idle", "no_change", "balanced"),
    ]
    content = build_policy_update_content(suggestions)
    assert content["changes"]["reflect"] == "decrease_frequency"
    assert "idle" not in content["changes"]
    assert len(content["suggestions"]) == 2
