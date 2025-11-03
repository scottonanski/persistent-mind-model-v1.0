"""Tests for impact_tracker.py - Enhanced Feedback Loop Phase 1A.

Tests cover:
- Deterministic action ID generation
- Action registration and impact measurement
- Effectiveness score calculation
- Impact signal identification
- Edge cases and error handling
"""

import os
import tempfile

from pmm.runtime.impact_tracker import (
    _clip_effectiveness,
    _compute_effectiveness_score,
    _generate_action_id,
    get_effectiveness_history,
    measure_impact,
    measure_pending_impacts,
    register_action,
)
from pmm.storage.eventlog import EventLog


class TestActionIdGeneration:
    """Test deterministic action ID generation."""

    def test_same_inputs_same_id(self):
        """Identical inputs should produce identical action IDs."""
        action_type = "commitment_open"
        action_data = {"content": "test commitment", "priority": "high"}
        tick_no = 123

        id1 = _generate_action_id(action_type, action_data, tick_no)
        id2 = _generate_action_id(action_type, action_data, tick_no)

        assert id1 == id2, "Same inputs should produce same action ID"
        assert isinstance(id1, int), "Action ID should be integer"
        assert id1 > 0, "Action ID should be positive"

    def test_different_inputs_different_ids(self):
        """Different inputs should produce different action IDs."""
        action_type = "commitment_open"
        tick_no = 123

        id1 = _generate_action_id(action_type, {"content": "test1"}, tick_no)
        id2 = _generate_action_id(action_type, {"content": "test2"}, tick_no)
        id3 = _generate_action_id("reflection", {"content": "test1"}, tick_no)
        id4 = _generate_action_id(action_type, {"content": "test1"}, 124)

        assert id1 != id2 != id3 != id4, "Different inputs should produce different IDs"

    def test_dict_order_independence(self):
        """Action ID should be independent of dictionary key order."""
        action_type = "commitment_open"
        tick_no = 123

        data1 = {"priority": "high", "content": "test"}
        data2 = {"content": "test", "priority": "high"}

        id1 = _generate_action_id(action_type, data1, tick_no)
        id2 = _generate_action_id(action_type, data2, tick_no)

        assert id1 == id2, "Dict order should not affect action ID"


class TestEffectivenessScore:
    """Test effectiveness score calculation."""

    def test_positive_deltas(self):
        """Positive IAS/GAS deltas should produce positive effectiveness."""
        score = _compute_effectiveness_score(0.05, 0.03)
        assert 0.0 < score <= 1.0
        assert score > 0.1, "Reasonable positive deltas should give >0.1 effectiveness"

    def test_zero_deltas(self):
        """Zero deltas should produce zero effectiveness."""
        score = _compute_effectiveness_score(0.0, 0.0)
        assert score == 0.0

    def test_negative_deltas(self):
        """Negative deltas should produce zero effectiveness (clipped)."""
        score = _compute_effectiveness_score(-0.05, -0.03)
        assert score == 0.0, "Negative deltas should be clipped to zero"

    def test_mixed_deltas(self):
        """Mixed deltas should use positive components only."""
        score1 = _compute_effectiveness_score(0.05, -0.02)  # IAS positive, GAS negative
        score2 = _compute_effectiveness_score(-0.02, 0.05)  # IAS negative, GAS positive
        score3 = _compute_effectiveness_score(0.03, 0.04)  # Both positive

        assert 0.0 < score1 < score3, "Mixed should be lower than both positive"
        assert 0.0 < score2 < score3, "Mixed should be lower than both positive"

    def test_ias_weighting(self):
        """IAS should have higher weight than GAS in effectiveness."""
        score_ias_only = _compute_effectiveness_score(0.05, 0.0)
        score_gas_only = _compute_effectiveness_score(0.0, 0.05)

        assert score_ias_only > score_gas_only, "IAS should have higher weight"


class TestEffectivenessClipping:
    """Test effectiveness score clipping to valid range."""

    def test_normal_range(self):
        """Values in normal range should pass through."""
        assert _clip_effectiveness(0.5) == 0.5
        assert _clip_effectiveness(0.0) == 0.0
        assert _clip_effectiveness(1.0) == 1.0

    def test_above_maximum(self):
        """Values above 1.0 should be clipped to 1.0."""
        assert _clip_effectiveness(1.5) == 1.0
        assert _clip_effectiveness(2.0) == 1.0

    def test_below_minimum(self):
        """Values below 0.0 should be clipped to 0.0."""
        assert _clip_effectiveness(-0.5) == 0.0
        assert _clip_effectiveness(-1.0) == 0.0

    def test_invalid_inputs(self):
        """Invalid inputs should default to minimum."""
        assert _clip_effectiveness(float("inf")) == 1.0  # infinity gets clipped to max
        assert _clip_effectiveness(float("nan")) == 0.0
        assert _clip_effectiveness(None) == 0.0


class TestActionRegistration:
    """Test action registration functionality."""

    def test_register_action_basic(self):
        """Basic action registration should succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            action_type = "commitment_open"
            action_data = {"content": "test commitment", "priority": "high"}
            tick_no = 123

            action_id = register_action(eventlog, action_type, action_data, tick_no)

            assert action_id > 0, "Should return valid action ID"

            # Verify action_initiated event was created
            events = eventlog.query(kind="action_initiated")
            assert len(events) == 1, "Should create one action_initiated event"

            event = events[0]
            meta = event.get("meta", {})
            assert meta.get("action_type") == action_type
            assert meta.get("action_id") == action_id
            assert meta.get("tick_no") == tick_no
            assert meta.get("action_data") == action_data
            assert "baseline_state" in meta

    def test_register_action_multiple(self):
        """Multiple actions should get different IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            action_id1 = register_action(
                eventlog, "commitment_open", {"content": "test1"}, 123
            )
            action_id2 = register_action(
                eventlog, "reflection", {"content": "test2"}, 124
            )

            assert (
                action_id1 != action_id2
            ), "Different actions should have different IDs"

            events = eventlog.query(kind="action_initiated")
            assert len(events) == 2, "Should create two action_initiated events"

    def test_register_action_with_baseline_state(self):
        """Action registration should capture baseline state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # First create an autonomy_tick for baseline state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.5, "GAS": 0.4, "open_commitments": 3}},
            )

            register_action(eventlog, "commitment_open", {"content": "test"}, 123)

            events = eventlog.query(kind="action_initiated")
            baseline_state = events[0].get("meta", {}).get("baseline_state", {})

            assert baseline_state.get("IAS") == 0.5
            assert baseline_state.get("GAS") == 0.4
            assert baseline_state.get("open_commitments") == 3


class TestImpactMeasurement:
    """Test impact measurement functionality."""

    def test_measure_impact_basic(self):
        """Basic impact measurement should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create baseline state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.5, "GAS": 0.4, "open_commitments": 3}},
            )

            # Register action
            action_id = register_action(
                eventlog, "commitment_open", {"content": "test"}, 123
            )

            # Create new state for impact measurement
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.55, "GAS": 0.45, "open_commitments": 4}},
            )

            impact = measure_impact(eventlog, action_id)

            assert impact.get("action_id") == action_id
            assert abs(impact.get("delta_ias") - 0.05) < 1e-10
            assert abs(impact.get("delta_gas") - 0.05) < 1e-10
            assert 0.0 < impact.get("effectiveness_score", 0) <= 1.0
            assert "impact_signals" in impact
            assert "baseline_state" in impact
            assert "current_state" in impact

    def test_measure_impact_nonexistent_action(self):
        """Measuring non-existent action should return error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            impact = measure_impact(eventlog, 99999)

            assert "error" in impact, "Should return error for non-existent action"

    def test_measure_impact_negative_deltas(self):
        """Negative deltas should result in low effectiveness."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create baseline state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.6, "GAS": 0.5, "open_commitments": 3}},
            )

            # Register action
            action_id = register_action(
                eventlog, "commitment_open", {"content": "test"}, 123
            )

            # Create worse state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.55, "GAS": 0.45, "open_commitments": 2}},
            )

            impact = measure_impact(eventlog, action_id)

            assert (
                abs(impact.get("delta_ias") + 0.05) < 1e-10
            )  # Allow for floating point precision
            assert abs(impact.get("delta_gas") + 0.05) < 1e-10
            assert (
                impact.get("effectiveness_score") == 0.0
            ), "Negative deltas should give zero effectiveness"


class TestEffectivenessHistory:
    """Test effectiveness history retrieval."""

    def test_get_effectiveness_history_empty(self):
        """Empty history should return empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            history = get_effectiveness_history(eventlog, "commitment_open")

            assert history == [], "Empty history should return empty list"

    def test_get_effectiveness_history_by_type(self):
        """History should be filtered by action type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create baseline state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.5, "GAS": 0.4, "open_commitments": 3}},
            )

            # Register different types of actions
            action_id1 = register_action(
                eventlog, "commitment_open", {"content": "commit1"}, 123
            )
            action_id2 = register_action(
                eventlog, "reflection", {"content": "reflect1"}, 124
            )

            # Create new state and measure impacts
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.55, "GAS": 0.45, "open_commitments": 4}},
            )

            # Manually create impact_measured events with proper structure
            eventlog.append(
                kind="impact_measured",
                content="",
                meta={
                    "action_id": action_id1,
                    "effectiveness_score": 0.7,
                    "delta_ias": 0.05,
                    "delta_gas": 0.05,
                    "impact_signals": ["commitment_close"],
                },
            )

            eventlog.append(
                kind="impact_measured",
                content="",
                meta={
                    "action_id": action_id2,
                    "effectiveness_score": 0.6,
                    "delta_ias": 0.04,
                    "delta_gas": 0.04,
                    "impact_signals": ["reflection"],
                },
            )

            # Get history for specific type
            commit_history = get_effectiveness_history(eventlog, "commitment_open")
            reflect_history = get_effectiveness_history(eventlog, "reflection")

            assert len(commit_history) == 1, "Should have one commitment record"
            assert len(reflect_history) == 1, "Should have one reflection record"

            assert commit_history[0]["action_id"] == action_id1
            assert reflect_history[0]["action_id"] == action_id2

    def test_get_effectiveness_history_limit(self):
        """History should respect limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create baseline state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.5, "GAS": 0.4, "open_commitments": 3}},
            )

            # Create multiple actions
            action_ids = []
            for i in range(5):
                action_id = register_action(
                    eventlog, "commitment_open", {"content": f"test{i}"}, 120 + i
                )
                action_ids.append(action_id)

                # Create new state
                eventlog.append(
                    kind="autonomy_tick",
                    content="",
                    meta={
                        "telemetry": {
                            "IAS": 0.55 + i * 0.01,
                            "GAS": 0.45 + i * 0.01,
                            "open_commitments": 4,
                        }
                    },
                )

                # Manually create impact_measured event
                eventlog.append(
                    kind="impact_measured",
                    content="",
                    meta={
                        "action_id": action_id,
                        "effectiveness_score": 0.7 + i * 0.01,
                        "delta_ias": 0.05,
                        "delta_gas": 0.05,
                        "impact_signals": ["commitment_close"],
                    },
                )

            history = get_effectiveness_history(eventlog, "commitment_open", limit=3)

            assert len(history) == 3, "Should respect limit"


class TestPendingImpacts:
    """Test pending impact measurement functionality."""

    def test_measure_pending_impacts_none_due(self):
        """No impacts should be measured if none are due."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Register recent action (not due yet)
            register_action(eventlog, "commitment_open", {"content": "test"}, 123)

            measured = measure_pending_impacts(
                eventlog, current_tick=125, window_ticks=10
            )

            assert measured == 0, "No impacts should be measured if not due"

    def test_measure_pending_impacts_due(self):
        """Due impacts should be measured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create baseline state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.5, "GAS": 0.4, "open_commitments": 3}},
            )

            # Register action that is now due (tick 100, window 10, current tick 115)
            register_action(eventlog, "commitment_open", {"content": "test"}, 100)

            # Create new state for impact measurement
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.55, "GAS": 0.45, "open_commitments": 4}},
            )

            # Measure pending impacts (window is 10, current tick is 115, so action at tick 100 is due)
            measured = measure_pending_impacts(
                eventlog, current_tick=115, window_ticks=10
            )

            assert measured == 1, "Should measure one due impact"

            # Verify impact_measured event was created
            impact_events = eventlog.query(kind="impact_measured")
            assert len(impact_events) == 1, "Should create impact_measured event"

    def test_measure_pending_impacts_no_duplicates(self):
        """Should not measure same impact twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create baseline state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.5, "GAS": 0.4, "open_commitments": 3}},
            )

            # Register action at tick 100
            register_action(eventlog, "commitment_open", {"content": "test"}, 100)

            # Create new state for impact measurement
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.55, "GAS": 0.45, "open_commitments": 4}},
            )

            # Measure pending impacts twice (first call should measure, second should not)
            measured1 = measure_pending_impacts(
                eventlog, current_tick=115, window_ticks=10
            )
            measured2 = measure_pending_impacts(
                eventlog, current_tick=120, window_ticks=10
            )

            assert measured1 == 1, "First call should measure impact"
            assert measured2 == 0, "Second call should not measure duplicate"

            # Should only have one impact_measured event
            impact_events = eventlog.query(kind="impact_measured")
            assert len(impact_events) == 1, "Should not create duplicate impact events"


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_register_action_error_handling(self):
        """Action registration should handle errors gracefully."""
        # Test with None eventlog (should not crash)
        action_id = register_action(None, "commitment_open", {"content": "test"}, 123)
        assert action_id == -1, "Should return -1 on error"

    def test_measure_impact_error_handling(self):
        """Impact measurement should handle errors gracefully."""
        # Test with None eventlog (should not crash)
        impact = measure_impact(None, 123)
        assert "error" in impact, "Should return error dict on failure"

    def test_get_effectiveness_history_error_handling(self):
        """History retrieval should handle errors gracefully."""
        # Test with None eventlog (should not crash)
        history = get_effectiveness_history(None, "commitment_open")
        assert history == [], "Should return empty list on error"

    def test_measure_pending_impacts_error_handling(self):
        """Pending impact measurement should handle errors gracefully."""
        # Test with None eventlog (should not crash)
        measured = measure_pending_impacts(None, 123)
        assert measured == 0, "Should return 0 on error"


class TestIntegration:
    """Integration tests for the complete impact tracking workflow."""

    def test_complete_workflow(self):
        """Test complete workflow from action registration to impact measurement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Initial state
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.4, "GAS": 0.3, "open_commitments": 2}},
            )

            # Register multiple actions at tick 100
            register_action(
                eventlog, "commitment_open", {"content": "test commit"}, 100
            )
            register_action(eventlog, "reflection", {"content": "test reflection"}, 100)

            # State changes for impact measurement
            eventlog.append(
                kind="autonomy_tick",
                content="",
                meta={"telemetry": {"IAS": 0.45, "GAS": 0.35, "open_commitments": 3}},
            )

            # Measure impacts when due (tick 115, window 10, actions at tick 100)
            measured = measure_pending_impacts(
                eventlog, current_tick=115, window_ticks=10
            )

            assert measured == 2, "Should measure both pending impacts"

            # Verify all events were created
            action_events = eventlog.query(kind="action_initiated")
            impact_events = eventlog.query(kind="impact_measured")

            assert len(action_events) == 2, "Should create two action_initiated events"
            assert len(impact_events) == 2, "Should create two impact_measured events"

            # Verify effectiveness scores were calculated
            for impact_event in impact_events:
                meta = impact_event.get("meta", {})
                assert "effectiveness_score" in meta
                assert "delta_ias" in meta
                assert "delta_gas" in meta

            # Check effectiveness history
            commit_history = get_effectiveness_history(eventlog, "commitment_open")
            reflect_history = get_effectiveness_history(eventlog, "reflection")

            assert len(commit_history) == 1, "Should have commitment history"
            assert len(reflect_history) == 1, "Should have reflection history"

            # Verify effectiveness scores are reasonable
            assert 0.0 < commit_history[0]["effectiveness_score"] <= 1.0
            assert 0.0 < reflect_history[0]["effectiveness_score"] <= 1.0
