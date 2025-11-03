"""Tests for Phase 3 experiment harness."""

import os
import tempfile

import pytest

from pmm.runtime.experiment_harness import (
    ExperimentHarness,
)
from pmm.storage.eventlog import EventLog


class TestExperimentHarness:
    """Test safe, deterministic experiment execution."""

    @pytest.fixture
    def eventlog(self):
        """Create temporary eventlog for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            eventlog = EventLog(db_path)
            yield eventlog
        finally:
            os.unlink(db_path)

    @pytest.fixture
    def harness(self, eventlog):
        """Create experiment harness with test eventlog."""
        return ExperimentHarness(eventlog, seed=42)

    def test_harness_initialization(self, harness):
        """Test harness initializes properly."""
        assert harness.eventlog is not None
        assert harness.seed == 42
        assert harness._max_concurrent == 2
        assert harness._max_horizon == 50
        assert harness._max_sample_size == 20
        assert len(harness._active_experiments) == 0

    def test_create_experiment_valid(self, harness):
        """Test creating a valid experiment."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Test communication style",
            description="Test if detailed responses improve satisfaction",
            arms=["control", "detailed"],
            traffic_split=[0.5, 0.5],
            metric="user_satisfaction",
        )

        assert experiment_id is not None
        assert experiment_id.startswith("exp_")
        assert experiment_id in harness._active_experiments

        state = harness.get_experiment_state(experiment_id)
        assert state is not None
        assert state.status == "pending"
        assert state.config.hypothesis_id == 123
        assert state.config.arms == ["control", "detailed"]
        assert state.config.traffic_split == [0.5, 0.5]

    def test_create_experiment_invalid_arms(self, harness):
        """Test rejecting experiment without control arm."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Invalid experiment",
            description="Missing control arm",
            arms=["variant_a", "variant_b"],  # No control
        )

        assert experiment_id is None

    def test_create_experiment_invalid_traffic_split(self, harness):
        """Test rejecting experiment with invalid traffic split."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Invalid split",
            description="Traffic split doesn't sum to 1",
            arms=["control", "variant"],
            traffic_split=[0.3, 0.8],  # Sum = 1.1
        )

        assert experiment_id is None

    def test_create_experiment_concurrent_limit(self, harness):
        """Test respecting concurrent experiment limit."""
        # Create experiments up to the limit
        experiment_ids = []
        for i in range(harness._max_concurrent):
            exp_id = harness.create_experiment(
                hypothesis_id=100 + i,
                name=f"Experiment {i}",
                description=f"Test experiment {i}",
                arms=["control", "variant"],
            )
            if exp_id:
                experiment_ids.append(exp_id)

        assert len(experiment_ids) == harness._max_concurrent

        # Try to create one more - should fail
        extra_id = harness.create_experiment(
            hypothesis_id=999,
            name="Extra experiment",
            description="Should exceed limit",
            arms=["control", "variant"],
        )

        assert extra_id is None

    def test_start_experiment(self, harness):
        """Test starting a pending experiment."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Test experiment",
            description="Test start functionality",
            arms=["control", "variant"],
        )

        assert experiment_id is not None

        # Start the experiment
        success = harness.start_experiment(experiment_id)
        assert success is True

        state = harness.get_experiment_state(experiment_id)
        assert state.status == "running"
        assert state.started_at is not None

    def test_start_nonexistent_experiment(self, harness):
        """Test starting non-existent experiment fails."""
        success = harness.start_experiment("nonexistent")
        assert success is False

    def test_deterministic_assignment(self, harness):
        """Test deterministic event assignment to arms."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Deterministic test",
            description="Test deterministic assignment",
            arms=["control", "variant_a", "variant_b"],
            traffic_split=[0.5, 0.3, 0.2],
        )

        harness.start_experiment(experiment_id)

        # Test deterministic assignment
        assignment1 = harness.assign_event(experiment_id, 1001)
        assignment2 = harness.assign_event(experiment_id, 1002)
        assignment3 = harness.assign_event(experiment_id, 1001)  # Same event ID

        # Same event ID should get same assignment
        assert assignment1 == assignment3

        # All assignments should be valid arms
        for assignment in [assignment1, assignment2]:
            assert assignment in ["control", "variant_a", "variant_b"]

    def test_assignment_sample_limits(self, harness):
        """Test assignment respects sample size limits."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Sample limit test",
            description="Test sample size limits",
            arms=["control", "variant"],
            sample_size=2,  # Very small limit
        )

        harness.start_experiment(experiment_id)

        # Assign events up to the limit
        assignments = []
        for i in range(10):  # Try to assign more than the limit
            assignment = harness.assign_event(experiment_id, 2000 + i)
            if assignment:
                assignments.append(assignment)

        state = harness.get_experiment_state(experiment_id)

        # Should not exceed sample limits
        assert state.current_samples["control"] <= 2
        assert state.current_samples["variant"] <= 2
        assert sum(state.current_samples.values()) <= 4

    def test_record_outcome(self, harness):
        """Test recording experiment outcomes."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Outcome test",
            description="Test outcome recording",
            arms=["control", "variant"],
        )

        harness.start_experiment(experiment_id)

        # Assign an event and record outcome
        event_id = 3001
        arm = harness.assign_event(experiment_id, event_id)
        assert arm is not None

        success = harness.record_outcome(experiment_id, event_id, 0.8)
        assert success is True

        state = harness.get_experiment_state(experiment_id)
        assert arm in state.outcomes
        assert 0.8 in state.outcomes[arm]

    def test_record_outcome_unassigned_event(self, harness):
        """Test recording outcome for unassigned event fails."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Unassigned test",
            description="Test outcome for unassigned event",
            arms=["control", "variant"],
        )

        harness.start_experiment(experiment_id)

        # Try to record outcome for unassigned event
        success = harness.record_outcome(experiment_id, 9999, 0.5)
        assert success is False

    def test_get_experiment_results(self, harness):
        """Test getting experiment results with statistical analysis."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Results test",
            description="Test results calculation",
            arms=["control", "variant"],
        )

        harness.start_experiment(experiment_id)

        # Add some test outcomes - use different event IDs to get different arms
        test_events = [
            (4000, "control"),
            (4001, "variant"),
            (4002, "control"),
            (4003, "variant"),
            (4004, "control"),
            (4005, "variant"),
        ]

        for event_id, expected_arm in test_events:
            # Keep trying different event IDs until we get the desired arm
            for attempt in range(100):
                test_event_id = event_id + attempt * 1000
                arm = harness.assign_event(experiment_id, test_event_id)
                if arm == expected_arm:
                    # Give variant better outcomes
                    metric_value = 0.5 if arm == "control" else 0.8
                    harness.record_outcome(experiment_id, test_event_id, metric_value)
                    break

        results = harness.get_experiment_results(experiment_id)
        assert results is not None
        assert len(results) >= 1  # At least one arm should have data

        # Check that we have results for the arms that got data
        arms_with_data = [r.arm for r in results]
        assert "control" in arms_with_data or "variant" in arms_with_data

        # If we have both arms, variant should show uplift
        control_result = next((r for r in results if r.arm == "control"), None)
        variant_result = next((r for r in results if r.arm == "variant"), None)

        if control_result and variant_result:
            assert variant_result.uplift > 0  # Should show improvement over control
            assert control_result.uplift == 0  # Control has no uplift

    def test_terminate_experiment(self, harness):
        """Test manual experiment termination."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Terminate test",
            description="Test manual termination",
            arms=["control", "variant"],
        )

        harness.start_experiment(experiment_id)

        # Terminate the experiment
        success = harness.terminate_experiment(experiment_id, "test_termination")
        assert success is True

        state = harness.get_experiment_state(experiment_id)
        assert state.status == "completed"
        assert state.completed_at is not None

    def test_get_active_experiments(self, harness):
        """Test retrieving active experiments."""
        # Create experiments up to the concurrent limit
        exp_ids = []
        max_experiments = min(
            3, harness._max_concurrent + 1
        )  # Try to create one more than limit

        for i in range(max_experiments):
            exp_id = harness.create_experiment(
                hypothesis_id=100 + i,
                name=f"Active test {i}",
                description=f"Test active experiments {i}",
                arms=["control", "variant"],
            )
            if exp_id:
                exp_ids.append(exp_id)

        # Start experiments that were created (at least one should exist)
        started_count = 0
        for exp_id in exp_ids:
            if harness.start_experiment(exp_id):
                started_count += 1

        active_experiments = harness.get_active_experiments()
        assert len(active_experiments) == started_count

        active_ids = [exp.config.experiment_id for exp in active_experiments]
        for i in range(started_count):
            assert exp_ids[i] in active_ids

    def test_experiment_horizon_termination(self, harness):
        """Test experiment terminates when horizon is reached."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Horizon test",
            description="Test horizon-based termination",
            arms=["control", "variant"],
            horizon=3,  # Very small horizon
        )

        harness.start_experiment(experiment_id)

        # Assign events up to and beyond horizon
        assignments = []
        for i in range(10):
            assignment = harness.assign_event(experiment_id, 5000 + i)
            if assignment:
                assignments.append(assignment)

        # Should have terminated due to horizon
        state = harness.get_experiment_state(experiment_id)
        assert state.status == "completed"

        # Total assignments should not exceed horizon
        total_assigned = sum(state.current_samples.values())
        assert total_assigned <= 3

    def test_cleanup_completed_experiments(self, harness):
        """Test cleanup of old completed experiments."""
        experiment_id = harness.create_experiment(
            hypothesis_id=123,
            name="Cleanup test",
            description="Test cleanup functionality",
            arms=["control", "variant"],
        )

        harness.start_experiment(experiment_id)
        harness.terminate_experiment(experiment_id, "test_cleanup")

        # Manually set old completion time
        state = harness._active_experiments[experiment_id]
        state.completed_at = "2023-01-01T00:00:00Z"

        # Run cleanup
        cleaned = harness.cleanup_completed_experiments(max_age_hours=1)
        assert cleaned >= 0

        # Experiment should be removed
        assert experiment_id not in harness._active_experiments
