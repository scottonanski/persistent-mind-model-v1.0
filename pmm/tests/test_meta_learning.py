# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_meta_learning.py
"""Tests for meta-learning subsystem."""


from pmm.core.event_log import EventLog
from pmm.meta_learning.efficiency_metrics import (
    EfficiencyMetrics,
    calculate_efficiency_metrics,
)
from pmm.meta_learning.optimization_engine import (
    MetaPolicySuggestion,
    build_meta_policy_update_content,
    suggest_meta_policy_changes,
)
from pmm.meta_learning.pattern_detector import (
    LearningPattern,
    detect_learning_patterns,
)


def test_detect_learning_patterns():
    """Test pattern detection."""
    log = EventLog(":memory:")
    log.append(kind="reflection", content='{"intent": "test"}')
    log.append(kind="policy_update", content="change")

    patterns = detect_learning_patterns(log, window=10)
    assert len(patterns) == 1
    p = patterns[0]
    assert p.name == "reflection_to_policy_update"
    assert p.count == 1
    assert p.avg_lag_events == 1.0  # event_id 2 - 1


def test_calculate_efficiency_metrics():
    """Test efficiency metrics calculation."""
    log = EventLog(":memory:")
    log.append(kind="policy_update", content="change")
    log.append(kind="assistant_message", content="COMMIT: task")
    log.append(kind="commitment_close", content="CLOSE: cid")

    patterns = [LearningPattern("reflection_to_policy_update", 1, 10.0)]
    metrics = calculate_efficiency_metrics(log, patterns, window=10)

    assert metrics.avg_reflection_to_policy_lag == 10.0
    assert metrics.policy_update_rate == 1 / 3  # 1 policy / 3 events
    assert metrics.commitment_resolution_rate == 1 / 2  # 1 close / 2 commits


def test_suggest_meta_policy_changes():
    """Test meta-policy suggestions."""
    efficiency = EfficiencyMetrics(
        avg_reflection_to_policy_lag=60.0,
        policy_update_rate=0.05,
        commitment_resolution_rate=0.8,
    )

    suggestions = suggest_meta_policy_changes(efficiency, stability_score=0.8)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.param == "reflection_interval"
    assert s.suggested_change == "decrease"

    # High policy rate, low stability
    efficiency2 = EfficiencyMetrics(10.0, 0.15, 0.8)
    suggestions2 = suggest_meta_policy_changes(efficiency2, stability_score=0.4)
    assert suggestions2[0].suggested_change == "increase"


def test_build_meta_policy_update_content():
    """Test building meta-policy update content."""
    suggestions = [
        MetaPolicySuggestion("reflection_interval", "decrease", "high lag"),
        MetaPolicySuggestion("summary_interval", "no_change", "balanced"),
    ]
    content = build_meta_policy_update_content(suggestions)
    assert content["changes"]["reflection_interval"] == "decrease"
    assert "summary_interval" not in content["changes"]
