# tests/test_evolution_reporter.py

import pytest

from pmm.constants import EventKinds
from pmm.runtime.evolution_reporter import EvolutionReporter
from pmm.storage.eventlog import EventLog


# Fixtures
@pytest.fixture
def empty_log(tmp_path):
    db = tmp_path / "elog.db"
    return EventLog(str(db))


@pytest.fixture
def seeded_log(empty_log):
    # Schema-safe events with proper meta fields
    empty_log.append(
        kind=EventKinds.COMMITMENT_OPEN,
        content="implement feature X",
        meta={"cid": "c1", "state": "open"},
    )
    empty_log.append(
        kind=EventKinds.REFLECTION,
        content="gained clarity on approach",
        meta={"tag": "clarity"},
    )
    empty_log.append(
        kind=EventKinds.TRAIT_UPDATE,
        content="trait update",
        meta={"trait": "openness", "delta": 0.05},
    )
    empty_log.append(
        kind=EventKinds.COMMITMENT_CLOSE,
        content="feature X completed",
        meta={"cid": "c1", "state": "closed"},
    )
    empty_log.append(
        kind=EventKinds.REFLECTION,
        content="improved engagement with task",
        meta={"tag": "engagement"},
    )
    empty_log.append(
        kind=EventKinds.TRAIT_UPDATE,
        content="trait update",
        meta={"trait": "conscientiousness", "delta": -0.02},
    )
    return empty_log


# Tests
def test_deterministic_summary_digest(seeded_log):
    """Same events should produce same summary digest."""
    er = EvolutionReporter(seeded_log)
    s1 = er.generate_summary(window=10)
    s2 = er.generate_summary(window=10)
    d1 = er._digest_summary(s1)
    d2 = er._digest_summary(s2)
    assert d1 == d2, "Identical summaries must produce identical digests"


def test_summary_schema_safety(seeded_log):
    """Summary should have expected structure and handle missing fields."""
    er = EvolutionReporter(seeded_log)
    summary = er.generate_summary(window=10)

    # Required top-level keys
    assert "reflections" in summary
    assert "traits" in summary
    assert "commitments" in summary

    # Check expected aggregations from meta fields only
    assert summary["reflections"]["clarity"] == 1
    assert summary["reflections"]["engagement"] == 1
    assert summary["traits"]["openness"] == 0.05
    assert summary["traits"]["conscientiousness"] == -0.02
    assert summary["commitments"]["open"] == 1
    assert summary["commitments"]["closed"] == 1


def test_emit_report_idempotency(seeded_log):
    """Same summary should not create duplicate events."""
    er = EvolutionReporter(seeded_log)
    summary = er.generate_summary(window=10)

    # First emission
    event_id1 = er.emit_evolution_report(summary)

    # Second emission with identical summary
    event_id2 = er.emit_evolution_report(summary)

    # Should return same event ID (no duplicate)
    assert (
        event_id1 == event_id2
    ), "Identical summaries should not create duplicate events"


def test_evolution_report_event_structure(seeded_log):
    """Evolution report events should have proper structure."""
    er = EvolutionReporter(seeded_log)
    summary = er.generate_summary(window=10)
    event_id = er.emit_evolution_report(summary)

    # Find the emitted event
    events = seeded_log.read_all()
    report_events = [e for e in events if e["kind"] == EventKinds.EVOLUTION]
    assert len(report_events) == 1

    event = report_events[0]
    assert event["id"] == event_id
    assert event["kind"] == EventKinds.EVOLUTION
    assert event["content"] == ""  # no semantic meaning in content

    # Check meta structure - all meaning in meta.changes
    meta = event["meta"]
    assert "digest" in meta
    assert "changes" in meta
    changes = meta["changes"]
    assert "reflections" in changes
    assert "traits" in changes
    assert "commitments" in changes


def test_empty_log_handling(empty_log):
    """Should handle empty logs gracefully."""
    er = EvolutionReporter(empty_log)
    summary = er.generate_summary(window=10)

    # Should have empty aggregations
    assert summary["reflections"] == {}
    assert summary["traits"] == {}
    assert summary["commitments"] == {}

    # Should NOT emit event for empty summary
    event_id = er.emit_evolution_report(summary)
    assert event_id is None


def test_missing_meta_fields(empty_log):
    """Should handle events with missing meta fields gracefully."""
    # Add events with minimal/missing meta
    empty_log.append(
        kind=EventKinds.REFLECTION,
        content="reflection without tag",
        meta={},  # Missing tag
    )
    empty_log.append(
        kind=EventKinds.TRAIT_UPDATE,
        content="trait update",
        meta={},  # Missing trait and delta
    )
    empty_log.append(
        kind=EventKinds.COMMITMENT_OPEN,
        content="commitment without state",
        meta={},  # Missing state
    )

    er = EvolutionReporter(empty_log)
    summary = er.generate_summary(window=10)

    # Should handle gracefully - only count events with proper meta fields
    assert len(summary["reflections"]) == 0  # no tag, so not counted
    assert len(summary["traits"]) == 0  # no trait name, so not counted
    assert len(summary["commitments"]) == 0  # no state, so not counted


def test_replay_consistency(seeded_log):
    """Same log should produce identical summaries across multiple runs."""
    er1 = EvolutionReporter(seeded_log)
    er2 = EvolutionReporter(seeded_log)

    s1 = er1.generate_summary(window=10)
    s2 = er2.generate_summary(window=10)

    assert s1 == s2, "Same log must produce identical summaries"
    assert er1._digest_summary(s1) == er2._digest_summary(s2), "Digests must match"


def test_window_limiting(seeded_log):
    """Window parameter should limit events considered."""
    er = EvolutionReporter(seeded_log)

    # Small window should see fewer events
    small_summary = er.generate_summary(window=2)
    full_summary = er.generate_summary(window=100)

    # Small window should have fewer or equal counts
    small_total = sum(small_summary["reflections"].values())
    full_total = sum(full_summary["reflections"].values())
    assert small_total <= full_total


def test_trait_delta_from_meta_only(empty_log):
    """Should only use trait deltas from meta fields, not content."""
    # Test meta delta only
    empty_log.append(
        kind=EventKinds.TRAIT_UPDATE,
        content="trait update",
        meta={"trait": "openness", "delta": 0.15},
    )

    # Test missing delta (should default to 0.0)
    empty_log.append(
        kind=EventKinds.TRAIT_UPDATE,
        content="trait update",
        meta={"trait": "conscientiousness"},  # no delta
    )

    er = EvolutionReporter(empty_log)
    summary = er.generate_summary(window=10)

    assert summary["traits"]["openness"] == 0.15
    assert summary["traits"]["conscientiousness"] == 0.0
