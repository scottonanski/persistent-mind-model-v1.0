"""Regression tests for IO helper schema consistency.

Validates that all three refactored event types emit proper structured payloads:
1. bandit_reward - includes 'component' field
2. reflection_forced - uses 'reason' (not 'forced_reflection_reason')
3. emergence_report - uses content="analysis" and structured meta

Tests ensure:
- Proper meta keys and types
- Content values are consistent
- Idempotency for emergence_report (duplicate digest handling)
"""

from __future__ import annotations

import pytest

from pmm.runtime.loop import io as _io
from pmm.runtime.emergence import EmergenceManager
from pmm.storage.eventlog import EventLog


class TestBanditRewardSchema:
    """Test bandit_reward event schema compliance."""

    def test_bandit_reward_includes_component(self, tmp_path):
        """Verify bandit_reward events include 'component' field in meta."""
        db_path = tmp_path / "test_bandit.db"
        eventlog = EventLog(str(db_path))

        # Emit bandit_reward using helper
        eid = _io.append_bandit_reward(
            eventlog,
            component="reflection",
            arm="succinct",
            reward=0.75,
        )

        # Verify event structure
        events = eventlog.read_all()
        assert len(events) == 1
        event = events[0]

        assert event["kind"] == "bandit_reward"
        assert event["content"] == ""
        assert "meta" in event

        meta = event["meta"]
        assert "component" in meta, "Missing required 'component' field"
        assert meta["component"] == "reflection"
        assert meta["arm"] == "succinct"
        assert meta["reward"] == 0.75

    def test_bandit_reward_optional_fields(self, tmp_path):
        """Verify optional fields (source, window, ref) are properly included."""
        db_path = tmp_path / "test_bandit_optional.db"
        eventlog = EventLog(str(db_path))

        eid = _io.append_bandit_reward(
            eventlog,
            component="planning",
            arm="detailed",
            reward=-0.25,
            source="quality_score",
            window=50,
            ref=123,
        )

        events = eventlog.read_all()
        meta = events[0]["meta"]

        assert meta["source"] == "quality_score"
        assert meta["window"] == 50
        assert meta["ref"] == 123

    def test_bandit_reward_type_coercion(self, tmp_path):
        """Verify type coercion for all fields."""
        db_path = tmp_path / "test_bandit_types.db"
        eventlog = EventLog(str(db_path))

        # Pass non-standard types that should be coerced
        _io.append_bandit_reward(
            eventlog,
            component=123,  # Should become "123"
            arm="test",
            reward="0.5",  # Should become 0.5
            window="100",  # Should become 100
        )

        events = eventlog.read_all()
        meta = events[0]["meta"]

        assert isinstance(meta["component"], str)
        assert isinstance(meta["reward"], float)
        assert isinstance(meta["window"], int)


class TestReflectionForcedSchema:
    """Test reflection_forced event schema compliance."""

    def test_reflection_forced_uses_reason_key(self, tmp_path):
        """Verify reflection_forced uses 'reason' not 'forced_reflection_reason'."""
        db_path = tmp_path / "test_forced.db"
        eventlog = EventLog(str(db_path))

        eid = _io.append_reflection_forced(
            eventlog,
            reason="identity_adopt",
        )

        events = eventlog.read_all()
        assert len(events) == 1
        event = events[0]

        assert event["kind"] == "reflection_forced"
        assert event["content"] == ""
        assert "meta" in event

        meta = event["meta"]
        assert "reason" in meta, "Must use 'reason' key (not 'forced_reflection_reason')"
        assert meta["reason"] == "identity_adopt"
        assert "forced_reflection_reason" not in meta, "Legacy key should not exist"

    def test_reflection_forced_optional_tick(self, tmp_path):
        """Verify optional 'tick' field is included when provided."""
        db_path = tmp_path / "test_forced_tick.db"
        eventlog = EventLog(str(db_path))

        _io.append_reflection_forced(
            eventlog,
            reason="low_gas",
            tick=42,
        )

        events = eventlog.read_all()
        meta = events[0]["meta"]

        assert "tick" in meta
        assert meta["tick"] == 42

    def test_reflection_forced_no_tick_omitted(self, tmp_path):
        """Verify 'tick' is omitted when None (not included as null)."""
        db_path = tmp_path / "test_forced_no_tick.db"
        eventlog = EventLog(str(db_path))

        _io.append_reflection_forced(
            eventlog,
            reason="test",
            tick=None,
        )

        events = eventlog.read_all()
        meta = events[0]["meta"]

        # tick should not be in meta at all when None
        assert "tick" not in meta


class TestEmergenceReportSchema:
    """Test emergence_report event schema compliance."""

    def test_emergence_report_content_is_analysis(self, tmp_path):
        """Verify emergence_report uses content='analysis' (not empty string)."""
        db_path = tmp_path / "test_emergence.db"
        eventlog = EventLog(str(db_path))

        metrics = {
            "ias_score": 0.65,
            "gas_score": 0.42,
            "commitment_score": 0.80,
            "reflection_score": 0.55,
            "composite_score": 0.61,
        }

        _io.append_emergence_report(
            eventlog,
            metrics=metrics,
            window_size=50,
            event_count=100,
            digest="abc123def456",
        )

        events = eventlog.read_all()
        assert len(events) == 1
        event = events[0]

        assert event["kind"] == "emergence_report"
        assert event["content"] == "analysis", "Must use 'analysis' not empty string"

    def test_emergence_report_meta_structure(self, tmp_path):
        """Verify emergence_report has proper meta structure."""
        db_path = tmp_path / "test_emergence_meta.db"
        eventlog = EventLog(str(db_path))

        metrics = {
            "ias_score": 0.5,
            "gas_score": 0.3,
            "commitment_score": 0.7,
            "reflection_score": 0.6,
            "composite_score": 0.55,
        }

        _io.append_emergence_report(
            eventlog,
            metrics=metrics,
            window_size=50,
            event_count=100,
            digest="test_digest_123",
            timestamp="2025-10-06T00:00:00Z",
        )

        events = eventlog.read_all()
        meta = events[0]["meta"]

        # Required fields
        assert "metrics" in meta
        assert "window_size" in meta
        assert "event_count" in meta
        assert "digest" in meta

        # Verify metrics structure
        assert isinstance(meta["metrics"], dict)
        assert "ias_score" in meta["metrics"]
        assert "gas_score" in meta["metrics"]
        assert "commitment_score" in meta["metrics"]
        assert "reflection_score" in meta["metrics"]
        assert "composite_score" in meta["metrics"]

        # Verify types
        assert isinstance(meta["window_size"], int)
        assert isinstance(meta["event_count"], int)
        assert isinstance(meta["digest"], str)
        assert meta["timestamp"] == "2025-10-06T00:00:00Z"

    def test_emergence_report_idempotency(self, tmp_path):
        """Verify EmergenceManager prevents duplicate reports with same digest."""
        db_path = tmp_path / "test_emergence_idem.db"
        eventlog = EventLog(str(db_path))

        # Seed with some events
        eventlog.append(kind="user", content="test", meta={})
        eventlog.append(kind="response", content="test response", meta={})

        manager = EmergenceManager(eventlog)

        # First emission should succeed
        events = eventlog.read_all()
        result1 = manager.emit_emergence_report(events)
        assert result1 is True

        # Second emission with same events should be skipped (idempotent)
        # Re-read events to include the emergence_report we just added
        events_with_report = eventlog.read_all()
        result2 = manager.emit_emergence_report(events_with_report)
        assert result2 is False

        # Verify only one emergence_report exists
        all_events = eventlog.read_all()
        emergence_reports = [e for e in all_events if e["kind"] == "emergence_report"]
        assert len(emergence_reports) == 1

    def test_emergence_report_different_digest_allowed(self, tmp_path):
        """Verify different digests allow new reports."""
        db_path = tmp_path / "test_emergence_diff.db"
        eventlog = EventLog(str(db_path))

        # Seed with initial events
        eventlog.append(kind="user", content="test1", meta={})
        manager = EmergenceManager(eventlog)

        # First emission
        events1 = eventlog.read_all()
        result1 = manager.emit_emergence_report(events1)
        assert result1 is True

        # Add new event (changes digest)
        eventlog.append(kind="user", content="test2", meta={})

        # Second emission with different events should succeed
        events2 = eventlog.read_all()
        result2 = manager.emit_emergence_report(events2)
        assert result2 is True

        # Verify two emergence_reports exist
        all_events = eventlog.read_all()
        emergence_reports = [e for e in all_events if e["kind"] == "emergence_report"]
        assert len(emergence_reports) == 2

        # Verify different digests
        digest1 = emergence_reports[0]["meta"]["digest"]
        digest2 = emergence_reports[1]["meta"]["digest"]
        assert digest1 != digest2


class TestSchemaConsistency:
    """Cross-cutting tests for schema consistency."""

    def test_all_helpers_use_empty_content_for_telemetry(self, tmp_path):
        """Verify telemetry events use empty content (not 'analysis')."""
        db_path = tmp_path / "test_consistency.db"
        eventlog = EventLog(str(db_path))

        # Telemetry events should have content=""
        _io.append_bandit_reward(
            eventlog, component="test", arm="test", reward=0.5
        )
        _io.append_reflection_forced(eventlog, reason="test")

        events = eventlog.read_all()
        assert events[0]["content"] == ""
        assert events[1]["content"] == ""

    def test_report_events_use_analysis_content(self, tmp_path):
        """Verify report events use content='analysis'."""
        db_path = tmp_path / "test_reports.db"
        eventlog = EventLog(str(db_path))

        metrics = {
            "ias_score": 0.5,
            "gas_score": 0.3,
            "commitment_score": 0.7,
            "reflection_score": 0.6,
            "composite_score": 0.55,
        }

        _io.append_emergence_report(
            eventlog,
            metrics=metrics,
            window_size=50,
            event_count=10,
            digest="test",
        )

        events = eventlog.read_all()
        assert events[0]["content"] == "analysis"
