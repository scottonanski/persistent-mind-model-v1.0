"""Tests for Advanced Emergence System (pmm/runtime/emergence.py)."""

from unittest.mock import Mock

from pmm.runtime.emergence import EmergenceManager, EmergenceScorer


class TestEmergenceScorer:
    """Test EmergenceScorer deterministic scoring."""

    def test_empty_events_returns_zero_scores(self):
        """Empty event list should return all zero scores."""
        scorer = EmergenceScorer()
        metrics = scorer.compute_emergence_metrics([])

        expected = {
            "ias_score": 0.0,
            "gas_score": 0.0,
            "commitment_score": 0.0,
            "reflection_score": 0.0,
            "composite_score": 0.0,
        }
        assert metrics == expected

    def test_deterministic_scoring_same_events(self):
        """Same events should produce identical scores."""
        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}}},
            {"kind": "commitment_open", "text": "test commitment"},
            {"kind": "commitment_close", "text": "test commitment"},
            {"kind": "reflection", "text": "analyzing current state and priorities"},
        ]

        scorer = EmergenceScorer()
        metrics1 = scorer.compute_emergence_metrics(events)
        metrics2 = scorer.compute_emergence_metrics(events)

        assert metrics1 == metrics2

    def test_ias_gas_extraction_from_telemetry(self):
        """Should extract IAS/GAS from most recent telemetry."""
        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.3, "GAS": 0.2}}},
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.7, "GAS": 0.5}}},
            {"kind": "reflection", "meta": {"telemetry": {"IAS": 0.8, "GAS": 0.6}}},
        ]

        scorer = EmergenceScorer()
        ias, gas = scorer._extract_ias_gas(events)

        # Should get most recent (reflection event)
        assert ias == 0.8
        assert gas == 0.6

    def test_ias_gas_fallback_defaults(self):
        """Should use fallback defaults when no telemetry available."""
        events = [
            {"kind": "commitment_open", "text": "test"},
            {"kind": "other_event", "text": "no telemetry"},
        ]

        scorer = EmergenceScorer()
        ias, gas = scorer._extract_ias_gas(events)

        assert ias == 0.28
        assert gas == 0.03

    def test_commitment_fulfillment_calculation(self):
        """Should calculate commitment fulfillment rate correctly."""
        events = [
            {"kind": "commitment_open", "text": "commit 1"},
            {"kind": "commitment_open", "text": "commit 2"},
            {"kind": "commitment_open", "text": "commit 3"},
            {"kind": "commitment_close", "text": "commit 1"},
            {"kind": "commitment_close", "text": "commit 2"},
        ]

        scorer = EmergenceScorer()
        score = scorer._compute_commitment_fulfillment(events)

        # 2 closes / 3 opens = 0.667
        assert abs(score - (2 / 3)) < 0.001

    def test_commitment_fulfillment_no_opens(self):
        """Should return neutral score when no commitments opened."""
        events = [
            {"kind": "reflection", "text": "thinking"},
            {"kind": "other_event", "text": "something"},
        ]

        scorer = EmergenceScorer()
        score = scorer._compute_commitment_fulfillment(events)

        assert score == 0.5

    def test_reflection_diversity_calculation(self):
        """Should calculate reflection diversity based on vocabulary richness."""
        events = [
            {"kind": "reflection", "text": "analyzing current state"},
            {"kind": "reflection", "text": "reviewing past decisions"},
            {"kind": "reflection", "text": "current state needs attention"},
        ]

        scorer = EmergenceScorer()
        score = scorer._compute_reflection_diversity(events)

        # Should be > 0 due to vocabulary diversity
        assert score > 0.0
        assert score <= 1.0

    def test_reflection_diversity_no_reflections(self):
        """Should return zero when no reflections present."""
        events = [
            {"kind": "commitment_open", "text": "test"},
            {"kind": "other_event", "text": "no reflections"},
        ]

        scorer = EmergenceScorer()
        score = scorer._compute_reflection_diversity(events)

        assert score == 0.0

    def test_z_score_normalization_deterministic(self):
        """Z-score normalization should be deterministic and bounded."""
        scorer = EmergenceScorer()

        # Test same inputs produce same outputs
        result1 = scorer._z_score_normalize(0.6, 0.5, 0.2)
        result2 = scorer._z_score_normalize(0.6, 0.5, 0.2)
        assert result1 == result2

        # Test bounds [0, 1]
        assert 0.0 <= result1 <= 1.0

        # Test zero std deviation
        result_zero_std = scorer._z_score_normalize(0.6, 0.5, 0.0)
        assert result_zero_std == 0.5

    def test_composite_score_weighting(self):
        """Composite score should use correct weighting formula."""
        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}}},
            {"kind": "commitment_open", "text": "test"},
            {"kind": "commitment_close", "text": "test"},
            {"kind": "reflection", "text": "diverse vocabulary analysis"},
        ]

        scorer = EmergenceScorer()
        metrics = scorer.compute_emergence_metrics(events)

        # Verify composite is weighted average
        expected_composite = (
            0.3 * metrics["ias_score"]
            + 0.3 * metrics["gas_score"]
            + 0.2 * metrics["commitment_score"]
            + 0.2 * metrics["reflection_score"]
        )

        assert abs(metrics["composite_score"] - expected_composite) < 0.001

    def test_window_size_limiting(self):
        """Should respect window size for event processing."""
        # Create more events than window size
        events = []
        for i in range(100):
            events.append({"kind": "test_event", "text": f"event {i}"})

        # Add telemetry at the end
        events.append(
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.8, "GAS": 0.7}}}
        )

        scorer = EmergenceScorer(window_size=50)
        metrics = scorer.compute_emergence_metrics(events)

        # Should still process successfully with window limiting
        assert metrics["composite_score"] >= 0.0


class TestEmergenceManager:
    """Test EmergenceManager report generation and stage weighting."""

    def test_generate_emergence_report_structure(self):
        """Generated report should have correct structure and digest."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {
                "kind": "autonomy_tick",
                "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}},
                "timestamp": "2024-01-01T00:00:00Z",
            }
        ]

        report = manager.generate_emergence_report(events)

        # Check required fields
        assert "metrics" in report
        assert "window_size" in report
        assert "event_count" in report
        assert "timestamp" in report
        assert "digest" in report

        # Check metrics structure
        metrics = report["metrics"]
        required_metrics = [
            "ias_score",
            "gas_score",
            "commitment_score",
            "reflection_score",
            "composite_score",
        ]
        for metric in required_metrics:
            assert metric in metrics

    def test_report_digest_deterministic(self):
        """Same events should produce same digest."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {
                "kind": "autonomy_tick",
                "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}},
                "timestamp": "2024-01-01T00:00:00Z",
            }
        ]

        report1 = manager.generate_emergence_report(events)
        report2 = manager.generate_emergence_report(events)

        assert report1["digest"] == report2["digest"]

    def test_report_digest_different_for_different_events(self):
        """Different events should produce different digests."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events1 = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}}}
        ]
        events2 = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.7, "GAS": 0.5}}}
        ]

        report1 = manager.generate_emergence_report(events1)
        report2 = manager.generate_emergence_report(events2)

        assert report1["digest"] != report2["digest"]

    def test_emit_emergence_report_idempotent(self):
        """Should not emit duplicate reports with same digest."""
        eventlog = Mock()
        eventlog.append = Mock()
        manager = EmergenceManager(eventlog)

        base_events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}}}
        ]

        # Generate report to get digest
        report = manager.generate_emergence_report(base_events)

        # Create events list with existing emergence_report with same digest
        events = base_events + [
            {"kind": "emergence_report", "meta": {"digest": report["digest"]}}
        ]

        # Try to emit - should return False (not emitted)
        result = manager.emit_emergence_report(events)
        assert not result
        eventlog.append.assert_not_called()

    def test_emit_emergence_report_new_digest(self):
        """Should emit report with new digest."""
        eventlog = Mock()
        eventlog.append = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}}},
            {"kind": "emergence_report", "meta": {"digest": "different_digest"}},
        ]

        result = manager.emit_emergence_report(events)
        assert result
        eventlog.append.assert_called_once()

        # Check call arguments
        call_args = eventlog.append.call_args
        assert call_args[0][0] == "emergence_report"
        assert call_args[0][1] == ""
        assert "digest" in call_args[0][2]

    def test_stage_transition_weight_upward(self):
        """Upward transitions should be weighted by emergence score."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.8, "GAS": 0.7}}}
        ]

        weight = manager.compute_stage_transition_weight("S1", "S2", events)

        # Should be positive (emergence score)
        assert weight > 0.0
        assert weight <= 1.0

    def test_stage_transition_weight_downward(self):
        """Downward transitions should be weighted by inverse emergence score."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.2, "GAS": 0.1}}}
        ]

        weight = manager.compute_stage_transition_weight("S2", "S1", events)

        # Should be high (1 - low_emergence_score)
        assert weight > 0.5
        assert weight <= 1.0

    def test_stage_transition_weight_same_stage(self):
        """Same stage should return neutral weight."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}}}
        ]

        weight = manager.compute_stage_transition_weight("S2", "S2", events)
        assert weight == 0.5

    def test_stage_transition_weight_unknown_stages(self):
        """Unknown stages should return neutral weight."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.6, "GAS": 0.4}}}
        ]

        weight = manager.compute_stage_transition_weight("UNKNOWN", "S2", events)
        assert weight == 0.5

        weight = manager.compute_stage_transition_weight("S2", "UNKNOWN", events)
        assert weight == 0.5

    def test_should_trigger_stage_evaluation_high_score(self):
        """High composite score should trigger evaluation."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.9, "GAS": 0.8}}},
            {"kind": "commitment_open", "text": "test"},
            {"kind": "commitment_close", "text": "test"},
            {"kind": "reflection", "text": "comprehensive analysis of current state"},
        ]

        should_trigger = manager.should_trigger_stage_evaluation(events)
        assert should_trigger

    def test_should_trigger_stage_evaluation_low_score(self):
        """Low composite score should trigger evaluation."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.1, "GAS": 0.05}}}
        ]

        should_trigger = manager.should_trigger_stage_evaluation(events)
        assert should_trigger

    def test_should_trigger_stage_evaluation_medium_score(self):
        """Medium composite score should not trigger evaluation."""
        eventlog = Mock()
        manager = EmergenceManager(eventlog)

        events = [
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.5, "GAS": 0.4}}}
        ]

        should_trigger = manager.should_trigger_stage_evaluation(events)
        assert not should_trigger


class TestEmergenceSystemIntegration:
    """Integration tests for complete emergence system."""

    def test_full_emergence_workflow(self):
        """Test complete emergence scoring and reporting workflow."""
        eventlog = Mock()
        eventlog.append = Mock()
        manager = EmergenceManager(eventlog)

        # Create realistic event sequence
        events = [
            {"kind": "identity_adopt", "text": "Echo", "meta": {"confidence": 0.9}},
            {"kind": "autonomy_tick", "meta": {"telemetry": {"IAS": 0.7, "GAS": 0.6}}},
            {"kind": "commitment_open", "text": "analyze system performance"},
            {
                "kind": "reflection",
                "text": "current system shows good autonomy metrics",
            },
            {"kind": "commitment_close", "text": "analysis complete"},
            {
                "kind": "reflection",
                "text": "performance analysis reveals optimization opportunities",
            },
        ]

        # Generate and emit report
        report = manager.generate_emergence_report(events)
        emitted = manager.emit_emergence_report(events)

        # Verify report structure
        assert "metrics" in report
        assert "digest" in report
        assert emitted

        # Verify metrics are reasonable
        metrics = report["metrics"]
        assert 0.0 <= metrics["composite_score"] <= 1.0
        assert metrics["commitment_score"] == 1.0  # Perfect fulfillment
        assert metrics["reflection_score"] > 0.0  # Has reflections

        # Verify stage evaluation
        should_eval = manager.should_trigger_stage_evaluation(events)
        assert isinstance(should_eval, bool)

        # Verify stage weighting
        weight = manager.compute_stage_transition_weight("S1", "S2", events)
        assert 0.0 <= weight <= 1.0

    def test_reproducible_across_runs(self):
        """Entire system should be reproducible across multiple runs."""
        eventlog1 = Mock()
        eventlog2 = Mock()

        manager1 = EmergenceManager(eventlog1)
        manager2 = EmergenceManager(eventlog2)

        events = [
            {
                "kind": "autonomy_tick",
                "meta": {"telemetry": {"IAS": 0.65, "GAS": 0.45}},
            },
            {"kind": "commitment_open", "text": "test commitment"},
            {
                "kind": "reflection",
                "text": "analyzing current state and future directions",
            },
        ]

        # Generate reports
        report1 = manager1.generate_emergence_report(events)
        report2 = manager2.generate_emergence_report(events)

        # Should be identical
        assert report1 == report2

        # Stage weights should be identical
        weight1 = manager1.compute_stage_transition_weight("S1", "S2", events)
        weight2 = manager2.compute_stage_transition_weight("S1", "S2", events)
        assert weight1 == weight2
