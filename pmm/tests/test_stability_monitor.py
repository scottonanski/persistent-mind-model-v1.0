# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_stability_monitor.py
"""Tests for stability monitor."""


from pmm.core.event_log import EventLog
from pmm.stability.stability_monitor import (
    build_stability_metrics_event_content,
    calculate_stability_metrics,
)


def test_calculate_stability_metrics():
    """Test metrics calculation with various events."""
    # Mock in-memory event log
    log = EventLog(":memory:")

    # Add events
    log.append(kind="user_message", content="Hello")
    log.append(kind="policy_update", content="Policy change")
    log.append(kind="assistant_message", content="Response\nCOMMIT: task")
    log.append(kind="commitment_close", content="CLOSE: cid123")
    log.append(kind="reflection", content="Reflection")
    log.append(kind="claim", content='CLAIM:type={"key": "value"}')

    metrics = calculate_stability_metrics(log, window=10)

    assert metrics["window_size"] == 10
    assert metrics["metrics"]["policy_change_rate"] == 1 / 6  # 1 policy_update
    assert metrics["metrics"]["commitment_churn"] == 2 / 6  # 1 commit + 1 close
    assert metrics["metrics"]["reflection_variance"] == 1 / 6  # 1 reflection
    assert 0.0 <= metrics["stability_score"] <= 1.0


def test_stability_metrics_determinism():
    """Test that metrics are deterministic."""
    log = EventLog(":memory:")
    log.append(kind="policy_update", content="Change")

    m1 = calculate_stability_metrics(log, window=5)
    m2 = calculate_stability_metrics(log, window=5)

    assert m1 == m2


def test_bounded_window():
    """Test that larger window changes metrics deterministically."""
    log = EventLog(":memory:")
    for i in range(10):
        log.append(kind="user_message", content=f"Msg {i}")
    log.append(kind="policy_update", content="Change")

    m_small = calculate_stability_metrics(log, window=5)
    m_large = calculate_stability_metrics(log, window=15)

    # Different windows give different rates
    assert (
        m_small["metrics"]["policy_change_rate"]
        > m_large["metrics"]["policy_change_rate"]
    )


def test_empty_log():
    """Test with empty or small log."""
    log = EventLog(":memory:")

    metrics = calculate_stability_metrics(log, window=10)
    assert metrics["stability_score"] == 1.0


def test_build_event_content():
    """Test building event content."""
    metrics = {
        "window_size": 100,
        "metrics": {"policy_change_rate": 0.1},
        "stability_score": 0.9,
    }
    content = build_stability_metrics_event_content(metrics)
    assert isinstance(content, dict)
    assert content["stability_score"] == 0.9
