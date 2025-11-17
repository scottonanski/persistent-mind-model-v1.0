# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for concept-level metrics."""

from pmm.core.event_log import EventLog
from pmm.core.concept_metrics import (
    compute_concept_metrics,
    get_governance_concepts,
    check_concept_health,
)


def test_compute_concept_metrics_empty():
    """Test metrics with no concepts."""
    log = EventLog(":memory:")
    metrics = compute_concept_metrics(log)

    assert metrics["concepts_used"] == {}
    assert metrics["concept_gaps"] == []
    assert metrics["concept_conflicts"] == []
    assert metrics["hot_concepts"] == []


def test_compute_concept_metrics_basic():
    """Test basic concept metrics."""
    log = EventLog(":memory:")

    e1 = log.append(kind="user_message", content="test1", meta={})
    e2 = log.append(kind="user_message", content="test2", meta={})

    log.append(
        kind="concept_define",
        content='{"token":"topic.a","concept_kind":"topic","definition":"topic a","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.b","concept_kind":"topic","definition":"topic b","attributes":{},"version":"1.0"}',
        meta={},
    )

    # Bind multiple events to topic.a
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.a"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.a"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Bind one event to topic.b (gap)
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.b"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    metrics = compute_concept_metrics(log)

    assert metrics["concepts_used"]["topic.a"] == 2
    assert metrics["concepts_used"]["topic.b"] == 1
    assert "topic.b" in metrics["concept_gaps"]  # < 2 bindings
    assert "topic.a" not in metrics["concept_gaps"]
    assert "topic.a" in metrics["hot_concepts"]


def test_get_governance_concepts():
    """Test governance concept filtering."""
    log = EventLog(":memory:")

    log.append(
        kind="concept_define",
        content='{"token":"policy.stability","concept_kind":"policy","definition":"stability policy","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"governance.commitment","concept_kind":"governance","definition":"commitment discipline","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.test","concept_kind":"topic","definition":"test topic","attributes":{},"version":"1.0"}',
        meta={},
    )

    governance = get_governance_concepts(log)

    assert "policy.stability" in governance
    assert "governance.commitment" in governance
    assert "topic.test" not in governance
    assert len(governance) == 2


def test_check_concept_health():
    """Test concept health check."""
    log = EventLog(":memory:")

    # Empty ledger
    health = check_concept_health(log)
    assert health["total_concepts"] == 0
    assert health["health_score"] == 0.0

    # Add concepts with good coverage
    e1 = log.append(kind="user_message", content="test1", meta={})
    e2 = log.append(kind="user_message", content="test2", meta={})

    log.append(
        kind="concept_define",
        content='{"token":"topic.a","concept_kind":"topic","definition":"topic a","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"policy.b","concept_kind":"policy","definition":"policy b","attributes":{},"version":"1.0"}',
        meta={},
    )

    # Good coverage (2+ bindings each)
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.a"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["topic.a"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["policy.b"],"relation":"discusses","weight":1.0}}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e2},"tokens":["policy.b"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    health = check_concept_health(log)

    assert health["total_concepts"] == 2
    assert health["total_bindings"] == 4
    assert health["avg_bindings_per_concept"] == 2.0
    assert health["governance_concept_count"] == 1
    assert health["gap_count"] == 0
    assert health["health_score"] == 1.0


def test_concept_conflicts():
    """Test conflict detection."""
    log = EventLog(":memory:")

    log.append(
        kind="concept_define",
        content='{"token":"topic.a","concept_kind":"topic","definition":"topic a","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.b","concept_kind":"topic","definition":"topic b","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_define",
        content='{"token":"topic.c","concept_kind":"topic","definition":"topic c","attributes":{},"version":"1.0"}',
        meta={},
    )

    # Create conflicting relations
    log.append(
        kind="concept_relate",
        content='{"from":"topic.a","to":"topic.b","relation":"supports","weight":1.0}',
        meta={},
    )
    log.append(
        kind="concept_relate",
        content='{"from":"topic.a","to":"topic.c","relation":"conflicts_with","weight":1.0}',
        meta={},
    )

    metrics = compute_concept_metrics(log)

    # topic.a has both supports and conflicts_with relations
    assert "topic.a" in metrics["concept_conflicts"]


def test_concept_metrics_determinism():
    """Test metrics are deterministic."""
    log = EventLog(":memory:")

    e1 = log.append(kind="user_message", content="test", meta={})

    log.append(
        kind="concept_define",
        content='{"token":"topic.test","concept_kind":"topic","definition":"test","attributes":{},"version":"1.0"}',
        meta={},
    )
    log.append(
        kind="concept_bind_event",
        content=f'{{"event_id":{e1},"tokens":["topic.test"],"relation":"discusses","weight":1.0}}',
        meta={},
    )

    # Compute multiple times
    metrics1 = compute_concept_metrics(log)
    metrics2 = compute_concept_metrics(log)
    metrics3 = compute_concept_metrics(log)

    assert metrics1 == metrics2 == metrics3

    health1 = check_concept_health(log)
    health2 = check_concept_health(log)
    health3 = check_concept_health(log)

    assert health1 == health2 == health3
