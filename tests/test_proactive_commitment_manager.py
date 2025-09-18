"""Tests for ProactiveCommitmentManager - only testing actual implemented code."""

import tempfile
import os
from pmm.storage.eventlog import EventLog
from pmm.commitments.manager import ProactiveCommitmentManager


class TestProactiveCommitmentManager:
    """Test suite for ProactiveCommitmentManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary database for each test
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.eventlog = EventLog(self.db_path)
        self.manager = ProactiveCommitmentManager()

    def teardown_method(self):
        """Clean up test fixtures."""
        if hasattr(self, "eventlog"):
            self.eventlog._conn.close()
        if hasattr(self, "temp_dir"):
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_deterministic_health_evaluation(self):
        """Given sequence of open/close events, verify correct metrics and determinism."""
        events = [
            {"id": 1, "kind": "commitment_open", "content": "commit1"},
            {"id": 2, "kind": "other_event", "content": "filler"},
            {"id": 3, "kind": "commitment_close", "content": "close1"},  # span = 2
            {"id": 4, "kind": "commitment_open", "content": "commit2"},
            {
                "id": 5,
                "kind": "commitment_open",
                "content": "commit3",
            },  # consecutive opens
            {
                "id": 6,
                "kind": "commitment_close",
                "content": "close2",
            },  # span = 2, closes commit2
        ]

        # Call twice to verify determinism
        health1 = self.manager.evaluate_commitment_health(events)
        health2 = self.manager.evaluate_commitment_health(events)

        assert health1 == health2

        # Verify metrics
        assert health1["total_opened"] == 3  # 3 opens
        assert health1["total_closed"] == 2  # 2 closes
        assert health1["close_rate"] == 2.0 / 3.0  # 2/3
        assert health1["avg_open_span"] == 2.0  # (2 + 2) / 2
        assert health1["streak_open_failures"] == 1  # commit3 still open

    def test_empty_events_handling(self):
        """Test behavior with empty event list."""
        health = self.manager.evaluate_commitment_health([])

        expected = {
            "total_opened": 0,
            "total_closed": 0,
            "close_rate": 0.0,
            "avg_open_span": -1.0,
            "streak_open_failures": 0,
        }

        assert health == expected

    def test_adjustment_suggestions_low_close_rate(self):
        """close_rate <0.5 → only shorten_ttl."""
        health = {
            "close_rate": 0.3,  # < 0.5
            "avg_open_span": 10.0,  # < 20
            "streak_open_failures": 1,  # < 3
        }

        suggestions = self.manager.suggest_commitment_adjustments(health)

        assert len(suggestions) == 1
        assert suggestions[0]["action"] == "shorten_ttl"
        assert suggestions[0]["reason"] == "low close rate"

    def test_adjustment_suggestions_long_spans(self):
        """avg_open_span >20 → only reinforce_reflection."""
        health = {
            "close_rate": 0.8,  # > 0.5
            "avg_open_span": 25.0,  # > 20
            "streak_open_failures": 1,  # < 3
        }

        suggestions = self.manager.suggest_commitment_adjustments(health)

        assert len(suggestions) == 1
        assert suggestions[0]["action"] == "reinforce_reflection"
        assert suggestions[0]["reason"] == "long spans"

    def test_adjustment_suggestions_multiple_failures(self):
        """streak_open_failures ≥3 → only cap_new_opens."""
        health = {
            "close_rate": 0.8,  # > 0.5
            "avg_open_span": 10.0,  # < 20
            "streak_open_failures": 3,  # >= 3
        }

        suggestions = self.manager.suggest_commitment_adjustments(health)

        assert len(suggestions) == 1
        assert suggestions[0]["action"] == "cap_new_opens"
        assert suggestions[0]["reason"] == "multiple failures"

    def test_adjustment_suggestions_healthy_stats(self):
        """Healthy stats → []."""
        health = {
            "close_rate": 0.8,  # > 0.5
            "avg_open_span": 15.0,  # < 20
            "streak_open_failures": 1,  # < 3
        }

        suggestions = self.manager.suggest_commitment_adjustments(health)

        assert suggestions == []

    def test_adjustment_suggestions_multiple_issues(self):
        """Multiple issues should generate multiple suggestions."""
        health = {
            "close_rate": 0.3,  # < 0.5 → shorten_ttl
            "avg_open_span": 25.0,  # > 20 → reinforce_reflection
            "streak_open_failures": 4,  # >= 3 → cap_new_opens
        }

        suggestions = self.manager.suggest_commitment_adjustments(health)

        assert len(suggestions) == 3
        actions = [s["action"] for s in suggestions]
        assert "shorten_ttl" in actions
        assert "reinforce_reflection" in actions
        assert "cap_new_opens" in actions

    def test_stable_digest_single_report_emission(self):
        """With empty log, maybe_emit_health_report appends one commitment_health."""
        health = {
            "total_opened": 5,
            "total_closed": 3,
            "close_rate": 0.6,
            "avg_open_span": 12.5,
            "streak_open_failures": 2,
        }

        event_id = self.manager.maybe_emit_health_report(self.eventlog, health)

        # Verify exactly one event was appended
        all_events = self.eventlog.read_all()
        assert len(all_events) == 1
        assert event_id is not None

        # Verify event structure
        event = all_events[0]
        assert event["kind"] == "commitment_health"
        assert event["content"] == "evaluation"

        meta = event["meta"]
        assert meta["component"] == "commitment_manager"
        assert meta["health"] == health
        assert meta["deterministic"] is True
        assert "digest" in meta

    def test_idempotent_rerun_same_health(self):
        """Re-running with same health dict appends zero additional events."""
        health = {
            "total_opened": 3,
            "total_closed": 2,
            "close_rate": 0.67,
            "avg_open_span": 8.0,
            "streak_open_failures": 1,
        }

        # First emission
        self.manager.maybe_emit_health_report(self.eventlog, health)
        events_after_first = len(self.eventlog.read_all())

        # Second emission with same health
        result = self.manager.maybe_emit_health_report(self.eventlog, health)
        events_after_second = len(self.eventlog.read_all())

        # Should have same number of events and return None
        assert events_after_first == events_after_second == 1
        assert result is None

    def test_digest_uniqueness(self):
        """Two different health dicts produce different digests → separate events."""
        health1 = {
            "total_opened": 3,
            "total_closed": 2,
            "close_rate": 0.67,
            "avg_open_span": 8.0,
            "streak_open_failures": 1,
        }

        health2 = {
            "total_opened": 4,  # Different value
            "total_closed": 2,
            "close_rate": 0.5,
            "avg_open_span": 8.0,
            "streak_open_failures": 1,
        }

        # Emit both health reports
        self.manager.maybe_emit_health_report(self.eventlog, health1)
        self.manager.maybe_emit_health_report(self.eventlog, health2)

        # Should have two events
        all_events = self.eventlog.read_all()
        assert len(all_events) == 2

        # Verify different digests
        digest1 = all_events[0]["meta"]["digest"]
        digest2 = all_events[1]["meta"]["digest"]
        assert digest1 != digest2

    def test_metadata_completeness(self):
        """Emitted event contains component, health, deterministic, and digest."""
        health = {
            "total_opened": 2,
            "total_closed": 1,
            "close_rate": 0.5,
            "avg_open_span": 5.0,
            "streak_open_failures": 0,
        }

        self.manager.maybe_emit_health_report(self.eventlog, health)

        # Get the emitted event
        events = self.eventlog.read_all()
        event = events[0]
        meta = event["meta"]

        # Verify all required keys are present
        required_keys = ["component", "health", "deterministic", "digest"]
        for key in required_keys:
            assert key in meta

        # Verify values
        assert meta["component"] == "commitment_manager"
        assert meta["health"] == health
        assert meta["deterministic"] is True
        assert isinstance(meta["digest"], str)
        assert len(meta["digest"]) == 64  # SHA256 hex length

    def test_complex_commitment_sequence(self):
        """Test complex sequence with reopens and multiple patterns."""
        events = [
            {"id": 1, "kind": "commitment_open", "content": "c1"},
            {"id": 2, "kind": "commitment_open", "content": "c2"},
            {"id": 3, "kind": "commitment_close", "content": "close_c1"},  # c1 span = 2
            {
                "id": 4,
                "kind": "commitment_reopen",
                "content": "reopen_c2",
            },  # counts as new open
            {
                "id": 5,
                "kind": "commitment_close",
                "content": "close_c2",
            },  # c2 original span = 3, reopen span = 1
            {"id": 6, "kind": "commitment_open", "content": "c3"},
            {"id": 7, "kind": "commitment_open", "content": "c4"},  # consecutive opens
        ]

        health = self.manager.evaluate_commitment_health(events)

        # total_opened: c1, c2, reopen_c2, c3, c4 = 5
        # total_closed: close_c1, close_c2 = 2
        # close_rate: 2/5 = 0.4
        # avg_open_span: FIFO matching: c1(pos0)->close(pos2)=span2, c2(pos1)->close(pos4)=span3, avg=(2+3)/2=2.5
        # streak_open_failures: 3 (reopen_c2, c3, c4 still open = 3 unmatched opens remaining)

        assert health["total_opened"] == 5
        assert health["total_closed"] == 2
        assert health["close_rate"] == 0.4
        assert health["avg_open_span"] == 2.5  # (2 + 3) / 2
        assert health["streak_open_failures"] == 3  # reopen_c2, c3, c4 still open

    def test_no_closes_scenario(self):
        """Test scenario with only opens, no closes."""
        events = [
            {"id": 1, "kind": "commitment_open", "content": "c1"},
            {"id": 2, "kind": "commitment_open", "content": "c2"},
            {"id": 3, "kind": "commitment_open", "content": "c3"},
        ]

        health = self.manager.evaluate_commitment_health(events)

        assert health["total_opened"] == 3
        assert health["total_closed"] == 0
        assert health["close_rate"] == 0.0  # 0 / max(1, 3) = 0
        assert health["avg_open_span"] == -1.0  # No closes
        assert health["streak_open_failures"] == 3  # All opens without close

    def test_digest_stability(self):
        """Same health dict should produce same digest across calls."""
        health = {
            "total_opened": 3,
            "total_closed": 2,
            "close_rate": 0.6666666666666666,
            "avg_open_span": 10.5,
            "streak_open_failures": 1,
        }

        digest1 = self.manager._calculate_health_digest(health)
        digest2 = self.manager._calculate_health_digest(health)

        assert digest1 == digest2
        assert isinstance(digest1, str)
        assert len(digest1) == 64  # SHA256 hex length
