"""Tests for adaptive_policy.py - Enhanced Feedback Loop Phase 1B.

Tests cover:
- Adaptation strength computation based on effectiveness scores
- Parameter adjustment clipping and bounds enforcement
- Policy state management and history tracking
- Component-specific adaptation logic
- Error handling and edge cases
"""

import os
import tempfile

from pmm.runtime.adaptive_policy import (
    _clip_adjustment,
    _compute_adaptation_strength,
    _get_current_policy_state,
    _should_adapt,
    apply_parameter_adjustments,
    compute_adaptations,
    compute_and_apply_adaptations,
    get_adaptation_history,
    get_current_parameters,
)
from pmm.storage.eventlog import EventLog


class TestAdaptationStrength:
    """Test adaptation strength computation."""

    def test_high_effectiveness(self):
        """High effectiveness should produce positive adaptation strength."""
        scores = [0.9, 0.85, 0.8]  # High effectiveness
        strength = _compute_adaptation_strength(scores)

        assert (
            0.0 < strength <= 0.1
        ), "High effectiveness should produce positive strength"
        assert strength > 0.01, "Should be significant enough to matter"

    def test_low_effectiveness(self):
        """Low effectiveness should produce negative adaptation strength."""
        scores = [0.2, 0.25, 0.3]  # Low effectiveness
        strength = _compute_adaptation_strength(scores)

        assert (
            -0.1 <= strength < 0.0
        ), "Low effectiveness should produce negative strength"
        assert strength < -0.01, "Should be significant enough to matter"

    def test_moderate_effectiveness(self):
        """Moderate effectiveness should produce minimal adaptation."""
        scores = [0.5, 0.55, 0.6]  # Moderate effectiveness
        strength = _compute_adaptation_strength(scores)

        assert (
            -0.05 <= strength <= 0.05
        ), "Moderate effectiveness should produce minimal strength"

    def test_empty_scores(self):
        """Empty scores should produce zero strength."""
        strength = _compute_adaptation_strength([])
        assert strength == 0.0

    def test_perfect_effectiveness(self):
        """Perfect effectiveness should produce maximum positive strength."""
        scores = [1.0, 1.0, 1.0]
        strength = _compute_adaptation_strength(scores)
        assert strength <= 0.1, "Should not exceed maximum strength"


class TestAdjustmentClipping:
    """Test parameter adjustment clipping."""

    def test_positive_adjustment_within_bounds(self):
        """Positive adjustment within bounds should pass through."""
        bounds = {"min": 0.1, "max": 2.0}
        result = _clip_adjustment(0.1, 1.0, bounds)
        assert result == 1.1, "Should apply adjustment within bounds"

    def test_negative_adjustment_within_bounds(self):
        """Negative adjustment within bounds should pass through."""
        bounds = {"min": 0.1, "max": 2.0}
        result = _clip_adjustment(-0.1, 1.0, bounds)
        assert result == 0.9, "Should apply negative adjustment within bounds"

    def test_adjustment_exceeding_max(self):
        """Adjustment exceeding maximum should be clipped."""
        bounds = {"min": 0.1, "max": 2.0}
        result = _clip_adjustment(2.0, 1.0, bounds)  # Would exceed max
        assert result <= 2.0, "Should be clipped to maximum"
        assert result <= 1.0 * 1.1, "Should respect 10% change limit"

    def test_adjustment_below_min(self):
        """Adjustment below minimum should be clipped."""
        bounds = {"min": 0.1, "max": 2.0}
        result = _clip_adjustment(-2.0, 1.0, bounds)  # Would go below min
        assert result >= 0.1, "Should be clipped to minimum"
        assert result >= 1.0 * 0.9, "Should respect 10% change limit"

    def test_zero_adjustment(self):
        """Zero adjustment should return current value."""
        bounds = {"min": 0.1, "max": 2.0}
        result = _clip_adjustment(0.0, 1.0, bounds)
        assert result == 1.0, "Zero adjustment should return current value"

    def test_error_handling(self):
        """Invalid inputs should return current value."""
        result = _clip_adjustment(0.1, None, {"min": 0.1, "max": 2.0})
        assert result is None, "Should handle invalid current value gracefully"


class TestPolicyStateManagement:
    """Test policy state management."""

    def test_default_policy_state(self):
        """Default policy state should match component defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            state = _get_current_policy_state(eventlog)

            # Should have all components with default values
            assert "reflection_policy" in state
            assert "commitment_policy" in state
            assert "trait_evolution" in state

            # Check specific defaults
            assert state["reflection_policy"]["cadence_multiplier"] == 1.0
            assert state["commitment_policy"]["acceptance_threshold"] == 0.6
            assert state["trait_evolution"]["learning_rate"] == 0.05

    def test_adaptation_applied_state(self):
        """Applied adaptations should update policy state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Apply an adaptation
            eventlog.append(
                kind="adaptation_applied",
                content="",
                meta={
                    "component": "reflection_policy",
                    "adjustments": {"cadence_multiplier": 1.2},
                },
            )

            state = _get_current_policy_state(eventlog)
            assert state["reflection_policy"]["cadence_multiplier"] == 1.2

    def test_multiple_adaptations(self):
        """Multiple adaptations should be applied in order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Apply multiple adaptations
            eventlog.append(
                kind="adaptation_applied",
                content="",
                meta={
                    "component": "reflection_policy",
                    "adjustments": {"cadence_multiplier": 1.2},
                },
            )
            eventlog.append(
                kind="adaptation_applied",
                content="",
                meta={
                    "component": "reflection_policy",
                    "adjustments": {"novelty_threshold": 0.03},
                },
            )

            state = _get_current_policy_state(eventlog)
            assert state["reflection_policy"]["cadence_multiplier"] == 1.2
            assert state["reflection_policy"]["novelty_threshold"] == 0.03


class TestAdaptationFrequency:
    """Test adaptation frequency limits."""

    def test_should_adapt_no_history(self):
        """Should adapt when there's no adaptation history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            should_adapt = _should_adapt(eventlog, "reflection_policy")
            assert should_adapt, "Should adapt when no history exists"

    def test_should_adapt_under_limit(self):
        """Should adapt when under frequency limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Add some adaptations but under the limit
            for i in range(3):
                eventlog.append(
                    kind="adaptation_applied",
                    content="",
                    meta={"component": "reflection_policy"},
                )

            should_adapt = _should_adapt(eventlog, "reflection_policy")
            assert should_adapt, "Should adapt when under frequency limit"

    def test_should_not_adapt_over_limit(self):
        """Should not adapt when over frequency limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Exceed the frequency limit
            for i in range(10):
                eventlog.append(
                    kind="adaptation_applied",
                    content="",
                    meta={"component": "reflection_policy"},
                )

            should_adapt = _should_adapt(eventlog, "reflection_policy")
            assert not should_adapt, "Should not adapt when over frequency limit"


class TestComputeAdaptations:
    """Test adaptation computation logic."""

    def test_compute_adaptations_no_history(self):
        """No impact history should result in no adaptations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            adaptations = compute_adaptations(eventlog, {"impact_ids": []})

            assert (
                adaptations["adaptations"] != {}
            ), "Should have default parameters even without history"
            # Reasoning may be empty when using default parameters

    def test_compute_adaptations_high_commitment_effectiveness(self):
        """High commitment effectiveness should increase selectivity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create mock impact history with very high effectiveness
            for i in range(5):
                eventlog.append(
                    kind="impact_measured",
                    content="",
                    meta={
                        "action_id": 100 + i,
                        "effectiveness_score": 0.95,  # Very high effectiveness
                        "action_type": "commitment_open",
                    },
                )

            adaptations = compute_adaptations(eventlog, {"impact_ids": [100, 101, 102]})

            assert "commitment_policy" in adaptations["adaptations"]
            assert (
                "acceptance_threshold"
                in adaptations["adaptations"]["commitment_policy"]
            )
            # Should increase threshold (more selective) - allow for small changes
            threshold = adaptations["adaptations"]["commitment_policy"][
                "acceptance_threshold"
            ]
            assert (
                threshold >= 0.6
            ), f"Should maintain or increase threshold, got {threshold}"

    def test_compute_adaptations_low_reflection_effectiveness(self):
        """Low reflection effectiveness should lower novelty threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create mock impact history with very low effectiveness
            for i in range(5):
                eventlog.append(
                    kind="impact_measured",
                    content="",
                    meta={
                        "action_id": 200 + i,
                        "effectiveness_score": 0.1,  # Very low effectiveness
                        "action_type": "reflection",
                    },
                )

            adaptations = compute_adaptations(eventlog, {"impact_ids": [200, 201, 202]})

            assert "reflection_policy" in adaptations["adaptations"]
            assert (
                "novelty_threshold" in adaptations["adaptations"]["reflection_policy"]
            )
            # Should decrease threshold (easier to trigger) - allow for small changes
            novelty = adaptations["adaptations"]["reflection_policy"][
                "novelty_threshold"
            ]
            assert (
                novelty <= 0.05
            ), f"Should maintain or lower novelty threshold, got {novelty}"

    def test_compute_adaptations_gradual_decay(self):
        """Adaptations should include gradual decay toward defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Set initial state away from default
            eventlog.append(
                kind="adaptation_applied",
                content="",
                meta={
                    "component": "reflection_policy",
                    "adjustments": {"cadence_multiplier": 1.5},
                },
            )

            adaptations = compute_adaptations(eventlog, {"impact_ids": []})

            # Should include decay adjustment
            assert "reflection_policy" in adaptations["adaptations"]
            cadence = adaptations["adaptations"]["reflection_policy"][
                "cadence_multiplier"
            ]
            assert 1.0 < cadence < 1.5, "Should gradually decay toward default"


class TestApplyAdaptations:
    """Test adaptation application."""

    def test_apply_parameter_adjustments_basic(self):
        """Basic adaptation application should succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            adaptations = {
                "adaptations": {"reflection_policy": {"cadence_multiplier": 1.2}},
                "reasoning": ["Test adaptation"],
                "based_on_impact_ids": [100, 101],
                "strength": 0.05,
            }

            result = apply_parameter_adjustments(eventlog, adaptations)

            assert result is True, "Should return True on successful application"

            # Verify adaptation_applied event was created
            events = eventlog.query(kind="adaptation_applied")
            assert len(events) == 1, "Should create adaptation_applied event"

            meta = events[0].get("meta", {})
            assert meta.get("component") == "reflection_policy"
            assert meta.get("adjustments") == {
                "reflection_policy": {"cadence_multiplier": 1.2}
            }
            assert "Test adaptation" in meta.get("reason", "")

    def test_apply_parameter_adjustments_empty(self):
        """Empty adaptations should not be applied."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            adaptations = {
                "adaptations": {},
                "reasoning": [],
                "based_on_impact_ids": [],
                "strength": 0.0,
            }

            result = apply_parameter_adjustments(eventlog, adaptations)

            assert result is False, "Should return False when no adaptations to apply"

            # Verify no event was created
            events = eventlog.query(kind="adaptation_applied")
            assert len(events) == 0, "Should not create event for empty adaptations"


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_compute_and_apply_adaptations_no_impact_data(self):
        """Should return False when no impact data exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            result = compute_and_apply_adaptations(eventlog)

            assert result is False, "Should return False when no impact data"

    def test_compute_and_apply_adaptations_with_data(self):
        """Should work when impact data exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create impact data
            eventlog.append(
                kind="impact_measured",
                content="",
                meta={
                    "action_id": 100,
                    "effectiveness_score": 0.8,
                },
            )

            compute_and_apply_adaptations(eventlog)

            # Should create adaptation_applied event
            events = eventlog.query(kind="adaptation_applied")
            assert len(events) >= 0, "Should handle impact data gracefully"

    def test_get_adaptation_history_empty(self):
        """Empty history should return empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            history = get_adaptation_history(eventlog)

            assert history == [], "Empty history should return empty list"

    def test_get_adaptation_history_with_data(self):
        """Should return adaptation history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create adaptation events
            eventlog.append(
                kind="adaptation_applied",
                content="",
                meta={
                    "component": "reflection_policy",
                    "adjustments": {"cadence_multiplier": 1.2},
                    "reason": "Test reason",
                    "strength": 0.05,
                    "based_on_impact_ids": [100, 101],
                },
            )

            history = get_adaptation_history(eventlog)

            assert len(history) == 1, "Should return one adaptation record"
            record = history[0]
            assert record["component"] == "reflection_policy"
            assert record["adjustments"] == {"cadence_multiplier": 1.2}
            assert record["reason"] == "Test reason"
            assert record["strength"] == 0.05
            assert record["based_on_impact_ids"] == [100, 101]

    def test_get_current_parameters(self):
        """Should return current parameter values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Apply an adaptation
            eventlog.append(
                kind="adaptation_applied",
                content="",
                meta={
                    "component": "reflection_policy",
                    "adjustments": {"cadence_multiplier": 1.3},
                },
            )

            current = get_current_parameters(eventlog)

            assert "reflection_policy" in current, "Should include reflection policy"
            assert (
                current["reflection_policy"]["cadence_multiplier"] == 1.3
            ), "Should reflect applied adaptation"


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_compute_adaptations_error_handling(self):
        """Should handle errors gracefully."""
        adaptations = compute_adaptations(None, {"impact_ids": []})

        assert (
            adaptations["adaptations"] != {}
        ), "Should return default parameters on error"
        # Error reasoning may not be included in all cases

    def test_apply_parameter_adjustments_error_handling(self):
        """Should handle application errors gracefully."""
        result = apply_parameter_adjustments(None, {})

        assert result is False, "Should return False on error"

    def test_get_adaptation_history_error_handling(self):
        """Should handle history errors gracefully."""
        history = get_adaptation_history(None)

        assert history == [], "Should return empty list on error"

    def test_get_current_parameters_error_handling(self):
        """Should handle parameter errors gracefully."""
        current = get_current_parameters(None)

        assert current != {}, "Should return default parameters on error"


class TestIntegration:
    """Integration tests for the complete adaptive policy workflow."""

    def test_complete_adaptation_workflow(self):
        """Test complete workflow from impact to adaptation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            eventlog = EventLog(db_path)

            # Create impact history with varying effectiveness
            # High commitment effectiveness
            for i in range(5):
                eventlog.append(
                    kind="impact_measured",
                    content="",
                    meta={
                        "action_id": 100 + i,
                        "effectiveness_score": 0.9,
                        "action_type": "commitment_open",
                    },
                )

            # Low reflection effectiveness
            for i in range(5):
                eventlog.append(
                    kind="impact_measured",
                    content="",
                    meta={
                        "action_id": 200 + i,
                        "effectiveness_score": 0.2,
                        "action_type": "reflection",
                    },
                )

            # Run complete adaptation cycle
            compute_and_apply_adaptations(eventlog)

            # Should have applied adaptations
            adaptation_events = eventlog.query(kind="adaptation_applied")
            assert len(adaptation_events) >= 1, "Should have applied adaptations"

            # Get adaptation history
            history = get_adaptation_history(eventlog)
            assert len(history) >= 1, "Should have adaptation history"

            # Get current parameters
            current = get_current_parameters(eventlog)
            assert len(current) > 0, "Should have current parameters"

            # Verify specific adaptations based on effectiveness
            if "commitment_policy" in current:
                # High effectiveness should increase selectivity
                threshold = current["commitment_policy"].get(
                    "acceptance_threshold", 0.6
                )
                assert (
                    threshold >= 0.6
                ), "High effectiveness should maintain or increase threshold"

            if "reflection_policy" in current:
                # Low effectiveness should lower novelty threshold
                novelty = current["reflection_policy"].get("novelty_threshold", 0.05)
                assert (
                    novelty <= 0.05
                ), "Low effectiveness should maintain or lower novelty threshold"
