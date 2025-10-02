"""Tests for SelfModelManager.

Validates deterministic self-model projection, idempotent consolidation,
and anomaly detection according to CONTRIBUTING.md principles.
"""

from unittest.mock import Mock

from pmm.personality.self_model_manager import SelfModelManager


class TestSelfModelManagerProjection:
    """Test deterministic self-model projection from events."""

    def test_baseline_projection_neutral_traits(self):
        """With no events, projection should return neutral baseline."""
        manager = SelfModelManager()
        model = manager.project_self_model([])

        traits = model["traits"]
        assert traits["O"] == 0.5
        assert traits["C"] == 0.5
        assert traits["E"] == 0.5
        assert traits["A"] == 0.5
        assert traits["N"] == 0.5

        assert model["event_count"] == 0
        assert model["last_update_id"] is None
        assert len(model["applied_events"]) == 0
        assert "digest" in model

    def test_trait_update_single_delta_accumulation(self):
        """Single trait_update events should accumulate properly."""
        events = [
            {"id": 1, "kind": "trait_update", "meta": {"trait": "O", "delta": 0.1}},
            {"id": 2, "kind": "trait_update", "meta": {"trait": "O", "delta": 0.05}},
            {"id": 3, "kind": "trait_update", "meta": {"trait": "C", "delta": -0.2}},
        ]

        manager = SelfModelManager()
        model = manager.project_self_model(events)

        traits = model["traits"]
        assert traits["O"] == 0.65  # 0.5 + 0.1 + 0.05
        assert traits["C"] == 0.3  # 0.5 - 0.2
        assert traits["E"] == 0.5  # unchanged
        assert traits["A"] == 0.5  # unchanged
        assert traits["N"] == 0.5  # unchanged

        assert model["event_count"] == 3
        assert model["last_update_id"] == 3

    def test_trait_update_multi_delta_format(self):
        """Multi-delta trait_update events should apply all deltas."""
        events = [
            {
                "id": 1,
                "kind": "trait_update",
                "meta": {"delta": {"O": 0.1, "C": -0.05, "E": 0.15}},
            }
        ]

        manager = SelfModelManager()
        model = manager.project_self_model(events)

        traits = model["traits"]
        assert traits["O"] == 0.6  # 0.5 + 0.1
        assert traits["C"] == 0.45  # 0.5 - 0.05
        assert traits["E"] == 0.65  # 0.5 + 0.15
        assert traits["A"] == 0.5  # unchanged
        assert traits["N"] == 0.5  # unchanged

        assert model["event_count"] == 3  # Three traits updated

    def test_policy_update_personality_changes(self):
        """policy_update events with personality changes should be applied."""
        events = [
            {
                "id": 1,
                "kind": "policy_update",
                "meta": {
                    "component": "personality",
                    "changes": [
                        {"trait": "O", "delta": 0.08},
                        {"trait": "A", "delta": -0.03},
                    ],
                },
            }
        ]

        manager = SelfModelManager()
        model = manager.project_self_model(events)

        traits = model["traits"]
        assert traits["O"] == 0.58  # 0.5 + 0.08
        assert traits["A"] == 0.47  # 0.5 - 0.03
        assert traits["C"] == 0.5  # unchanged
        assert traits["E"] == 0.5  # unchanged
        assert traits["N"] == 0.5  # unchanged

    def test_evolution_events_absolute_values(self):
        """evolution events should set absolute trait values."""
        events = [
            {
                "id": 1,
                "kind": "evolution",
                "meta": {
                    "changes": {
                        "traits.O": 0.75,
                        "traits.C": 0.25,
                        "other.setting": "ignored",
                    }
                },
            }
        ]

        manager = SelfModelManager()
        model = manager.project_self_model(events)

        traits = model["traits"]
        assert traits["O"] == 0.75
        assert traits["C"] == 0.25
        assert traits["E"] == 0.5  # unchanged
        assert traits["A"] == 0.5  # unchanged
        assert traits["N"] == 0.5  # unchanged

    def test_trait_clamping_to_bounds(self):
        """Traits should be clamped to [0.0, 1.0] bounds."""
        events = [
            {
                "id": 1,
                "kind": "trait_update",
                "meta": {"trait": "O", "delta": 0.8},  # 0.5 + 0.8 = 1.3 -> 1.0
            },
            {
                "id": 2,
                "kind": "trait_update",
                "meta": {"trait": "C", "delta": -0.9},  # 0.5 - 0.9 = -0.4 -> 0.0
            },
        ]

        manager = SelfModelManager()
        model = manager.project_self_model(events)

        traits = model["traits"]
        assert traits["O"] == 1.0  # clamped to upper bound
        assert traits["C"] == 0.0  # clamped to lower bound

    def test_deterministic_digest_generation(self):
        """Same trait values should produce same digest."""
        events = [
            {"id": 1, "kind": "trait_update", "meta": {"trait": "O", "delta": 0.1}}
        ]

        manager = SelfModelManager()
        model1 = manager.project_self_model(events)
        model2 = manager.project_self_model(events)

        assert model1["digest"] == model2["digest"]
        assert len(model1["digest"]) == 64  # SHA256 hex length

    def test_replayability_identical_results(self):
        """Same events should produce identical models."""
        events = [
            {"id": 1, "kind": "trait_update", "meta": {"trait": "O", "delta": 0.1}},
            {
                "id": 2,
                "kind": "policy_update",
                "meta": {
                    "component": "personality",
                    "changes": [{"trait": "C", "delta": -0.05}],
                },
            },
        ]

        manager = SelfModelManager()
        model1 = manager.project_self_model(events)
        model2 = manager.project_self_model(events)

        assert model1["traits"] == model2["traits"]
        assert model1["digest"] == model2["digest"]
        assert model1["event_count"] == model2["event_count"]


class TestSelfModelManagerConsolidation:
    """Test idempotent consolidation with self_model_update events."""

    def test_consolidate_emits_self_model_update_event(self):
        """consolidate() should emit self_model_update event with proper structure."""
        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = []
        mock_eventlog.append.return_value = "event_123"

        current_model = {
            "traits": {"O": 0.6, "C": 0.4, "E": 0.5, "A": 0.5, "N": 0.5},
            "digest": "abc123def456",
            "applied_events": [{"event_id": 1}],
            "last_update_id": 1,
        }

        manager = SelfModelManager()
        event_id = manager.consolidate(mock_eventlog, "src_event_42", current_model)

        assert event_id == "event_123"
        mock_eventlog.append.assert_called_once()

        call_args = mock_eventlog.append.call_args
        assert call_args[1]["kind"] == "self_model_update"
        assert call_args[1]["content"] == "projection"

        meta = call_args[1]["meta"]
        assert meta["component"] == "self_model_manager"
        assert meta["traits"] == current_model["traits"]
        assert meta["digest"] == "abc123def456"
        assert meta["src_event_id"] == "src_event_42"
        assert meta["deterministic"] is True

    def test_consolidate_idempotent_skips_duplicate_digest(self):
        """consolidate() should skip if event with same digest already exists."""
        existing_events = [
            {"kind": "self_model_update", "meta": {"digest": "abc123def456"}}
        ]

        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = existing_events

        current_model = {
            "traits": {"O": 0.6, "C": 0.4, "E": 0.5, "A": 0.5, "N": 0.5},
            "digest": "abc123def456",  # Same digest as existing
        }

        manager = SelfModelManager()
        event_id = manager.consolidate(mock_eventlog, "src_event_42", current_model)

        assert event_id is None  # Should skip
        mock_eventlog.append.assert_not_called()

    def test_consolidate_emits_when_digest_differs(self):
        """consolidate() should emit when digest is different from existing."""
        existing_events = [
            {"kind": "self_model_update", "meta": {"digest": "old_digest_123"}}
        ]

        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = existing_events
        mock_eventlog.append.return_value = "event_456"

        current_model = {
            "traits": {"O": 0.7, "C": 0.3, "E": 0.5, "A": 0.5, "N": 0.5},
            "digest": "new_digest_456",  # Different digest
        }

        manager = SelfModelManager()
        event_id = manager.consolidate(mock_eventlog, "src_event_99", current_model)

        assert event_id == "event_456"
        mock_eventlog.append.assert_called_once()


class TestSelfModelManagerAnomalyDetection:
    """Test anomaly detection for drift patterns."""

    def test_detect_anomalies_empty_history(self):
        """Empty history should return no anomalies."""
        manager = SelfModelManager()
        anomalies = manager.detect_anomalies([])

        assert anomalies == []

    def test_detect_trait_out_of_bounds(self):
        """Traits outside [0,1] should be flagged as anomalies."""
        history = [
            {
                "traits": {
                    "O": 1.5,  # Out of bounds
                    "C": -0.2,  # Out of bounds
                    "E": 0.5,
                    "A": 0.5,
                    "N": 0.5,
                }
            }
        ]

        manager = SelfModelManager()
        anomalies = manager.detect_anomalies(history)

        assert "trait_out_of_bounds:O:1.500" in anomalies
        assert "trait_out_of_bounds:C:-0.200" in anomalies
        assert len(anomalies) == 2

    def test_detect_sudden_jump_between_updates(self):
        """Sudden jumps >0.2 between consecutive updates should be flagged."""
        history = [
            {"traits": {"O": 0.3, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}},
            {
                "traits": {
                    "O": 0.8,  # Jump of 0.5 > 0.2
                    "C": 0.5,
                    "E": 0.5,
                    "A": 0.5,
                    "N": 0.5,
                }
            },
        ]

        manager = SelfModelManager()
        anomalies = manager.detect_anomalies(history)

        assert any("sudden_jump:O:0.500" in anomaly for anomaly in anomalies)

    def test_detect_oscillation_pattern(self):
        """Repeated oscillation >3 times should be flagged."""
        # Create oscillating pattern: 0.5 -> 0.7 -> 0.3 -> 0.8 -> 0.2 -> 0.9
        history = []
        values = [0.5, 0.7, 0.3, 0.8, 0.2, 0.9, 0.1, 0.95]

        for i, val in enumerate(values):
            history.append(
                {"traits": {"O": val, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}}
            )

        manager = SelfModelManager()
        anomalies = manager.detect_anomalies(history)

        # Should detect oscillation in trait O
        assert any("oscillation:O:" in anomaly for anomaly in anomalies)

    def test_no_anomalies_for_normal_drift(self):
        """Normal gradual drift should not trigger anomalies."""
        history = [
            {"traits": {"O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}},
            {"traits": {"O": 0.55, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}},
            {"traits": {"O": 0.6, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}},
            {"traits": {"O": 0.65, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}},
        ]

        manager = SelfModelManager()
        anomalies = manager.detect_anomalies(history)

        assert anomalies == []


class TestSelfModelManagerIntegration:
    """Test integration workflow and metadata integrity."""

    def test_full_workflow_project_and_consolidate(self):
        """Test complete workflow: project -> consolidate."""
        events = [
            {"id": 1, "kind": "trait_update", "meta": {"trait": "O", "delta": 0.1}},
            {"id": 2, "kind": "trait_update", "meta": {"trait": "C", "delta": -0.05}},
        ]

        mock_eventlog = Mock()
        mock_eventlog.read_all.return_value = []
        mock_eventlog.append.return_value = "consolidation_event_123"

        manager = SelfModelManager()

        # Project current model
        model = manager.project_self_model(events)
        assert model["traits"]["O"] == 0.6
        assert model["traits"]["C"] == 0.45

        # Consolidate model
        event_id = manager.consolidate(mock_eventlog, "trigger_event_2", model)
        assert event_id == "consolidation_event_123"

        # Verify consolidation call
        call_args = mock_eventlog.append.call_args
        meta = call_args[1]["meta"]
        assert meta["traits"]["O"] == 0.6
        assert meta["traits"]["C"] == 0.45
        assert meta["src_event_id"] == "trigger_event_2"

    def test_metadata_integrity_preservation(self):
        """Metadata should be preserved correctly throughout projection."""
        events = [
            {"id": 10, "kind": "trait_update", "meta": {"trait": "E", "delta": 0.2}},
            {
                "id": 15,
                "kind": "policy_update",
                "meta": {
                    "component": "personality",
                    "changes": [{"trait": "A", "delta": 0.1}],
                },
            },
        ]

        manager = SelfModelManager()
        model = manager.project_self_model(events)

        applied_events = model["applied_events"]
        assert len(applied_events) == 2

        # Check first event metadata
        assert applied_events[0]["event_id"] == 10
        assert applied_events[0]["trait"] == "E"
        assert applied_events[0]["delta"] == 0.2
        assert applied_events[0]["source"] == "trait_update"

        # Check second event metadata
        assert applied_events[1]["event_id"] == 15
        assert applied_events[1]["trait"] == "A"
        assert applied_events[1]["delta"] == 0.1
        assert applied_events[1]["source"] == "policy_update"

        assert model["last_update_id"] == 15
