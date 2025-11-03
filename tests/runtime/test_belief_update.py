"""Tests for Phase 3 belief update system."""

import os
import tempfile

import pytest

from pmm.runtime.belief_update import BeliefUpdate, BeliefUpdateBatch
from pmm.runtime.experiment_harness import ExperimentHarness
from pmm.runtime.hypothesis_tracker import HypothesisTracker
from pmm.storage.eventlog import EventLog


class TestBeliefUpdate:
    """Test bounded, auditable belief updates."""

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
    def belief_update(self, eventlog):
        """Create belief update system with test eventlog."""
        return BeliefUpdate(eventlog)

    @pytest.fixture
    def hypothesis_tracker(self, eventlog):
        """Create hypothesis tracker for testing."""
        return HypothesisTracker(eventlog)

    @pytest.fixture
    def experiment_harness(self, eventlog):
        """Create experiment harness for testing."""
        return ExperimentHarness(eventlog)

    def test_belief_update_initialization(self, belief_update):
        """Test belief update system initializes with default policies."""
        assert belief_update.eventlog is not None
        assert belief_update.scorer is not None
        assert belief_update.max_delta_per_update == 0.1
        assert len(belief_update.policies) > 0

        # Check default policies exist
        assert "response_detail_level" in belief_update.policies
        assert "technical_explanation_depth" in belief_update.policies
        assert "proactive_question_frequency" in belief_update.policies
        assert "reflection_frequency" in belief_update.policies
        assert "commitment_ambition" in belief_update.policies

    def test_get_policy(self, belief_update):
        """Test retrieving policy parameters."""
        policy = belief_update.get_policy("response_detail_level")
        assert policy is not None
        assert policy.key == "response_detail_level"
        assert 0.1 <= policy.current_value <= 1.0
        assert policy.min_value == 0.1
        assert policy.max_value == 1.0

        # Non-existent policy should return None
        policy = belief_update.get_policy("nonexistent")
        assert policy is None

    def test_update_policy_valid(self, belief_update):
        """Test valid policy update with bounds checking."""
        success = belief_update.update_policy(
            policy_key="response_detail_level", new_value=0.8, reason="Test update"
        )

        assert success is True

        policy = belief_update.get_policy("response_detail_level")
        assert policy.current_value == 0.8
        assert policy.last_updated is not None
        assert len(policy.update_history) > 0

        # Check update was logged
        latest_update = policy.update_history[-1]
        assert latest_update[0] == 0.8  # New value
        assert "Test update" in latest_update[2]  # Reason

    def test_update_policy_bounds(self, belief_update):
        """Test policy updates respect bounds."""
        policy = belief_update.get_policy("response_detail_level")

        # Try to set below minimum
        success = belief_update.update_policy(
            policy_key="response_detail_level",
            new_value=0.0,  # Below min of 0.1
            reason="Below minimum",
        )
        assert success is True
        assert policy.current_value == 0.1  # Should be clamped to minimum

        # Try to set above maximum
        success = belief_update.update_policy(
            policy_key="response_detail_level",
            new_value=1.5,  # Above max of 1.0
            reason="Above maximum",
        )
        assert success is True
        assert policy.current_value == 1.0  # Should be clamped to maximum

    def test_update_policy_nonexistent(self, belief_update):
        """Test updating non-existent policy fails."""
        success = belief_update.update_policy(
            policy_key="nonexistent_policy", new_value=0.5, reason="Should fail"
        )
        assert success is False

    def test_update_policy_small_change(self, belief_update):
        """Test very small changes are ignored."""
        policy = belief_update.get_policy("response_detail_level")
        original_value = policy.current_value

        # Try very small change
        success = belief_update.update_policy(
            policy_key="response_detail_level",
            new_value=original_value + 0.001,  # Very small change
            reason="Tiny change",
        )
        assert success is False  # Should be rejected as too small
        assert policy.current_value == original_value

    def test_get_current_policies(self, belief_update):
        """Test getting all current policy values."""
        policies = belief_update.get_current_policies()

        assert isinstance(policies, dict)
        assert len(policies) == len(belief_update.policies)

        for key, value in policies.items():
            assert key in belief_update.policies
            assert isinstance(value, float)
            assert 0.0 <= value <= 1.0  # All policies should be in reasonable range

    def test_compute_updates_from_evidence_empty(
        self, belief_update, hypothesis_tracker, experiment_harness
    ):
        """Test computing updates with no evidence."""
        updates = belief_update.compute_updates_from_evidence(
            hypothesis_tracker, experiment_harness
        )
        assert updates == []  # No evidence should mean no updates

    def test_compute_updates_from_hypothesis(
        self, belief_update, hypothesis_tracker, experiment_harness
    ):
        """Test computing updates from supported hypothesis."""
        # Create a supported hypothesis about communication
        hypothesis = hypothesis_tracker.create_hypothesis(
            statement="If users ask questions then I provide detailed responses within 5 events measured by response_quality",
            priors=0.8,
            evidence_tokens=["[1:acf76915]"],
        )

        if hypothesis:
            # Add enough evidence to make it supported
            for _ in range(15):
                hypothesis_tracker.add_evidence(hypothesis.id, True, 0.9)

            updates = belief_update.compute_updates_from_evidence(
                hypothesis_tracker, experiment_harness
            )

            # Should find at least one update related to communication
            communication_updates = [
                u
                for u in updates
                if "response" in u.policy_key or "detail" in u.policy_key
            ]
            assert len(communication_updates) > 0

    def test_apply_belief_updates(self, belief_update):
        """Test applying a batch of belief updates."""
        from pmm.runtime.scoring import BeliefDelta

        # Create test updates
        updates = [
            BeliefDelta(
                policy_key="response_detail_level",
                before_value=0.5,
                delta=0.1,
                after_value=0.6,
                basis_hypothesis_id=123,
                confidence=0.8,
                timestamp="2025-01-01T00:00:00Z",
            ),
            BeliefDelta(
                policy_key="technical_explanation_depth",
                before_value=0.5,
                delta=-0.1,
                after_value=0.4,
                basis_hypothesis_id=124,
                confidence=0.7,
                timestamp="2025-01-01T00:00:00Z",
            ),
        ]

        batch = belief_update.apply_belief_updates(updates, "Test batch")

        assert isinstance(batch, BeliefUpdateBatch)
        assert batch.batch_id.startswith("batch_")
        assert len(batch.updates) <= 2  # Some updates might be rejected
        assert batch.total_delta > 0

        # Check policies were actually updated
        if batch.updates:
            for update in batch.updates:
                policy = belief_update.get_policy(update.policy_key)
                assert policy.current_value == update.after_value

    def test_get_policy_stability_metrics(self, belief_update):
        """Test policy stability calculation."""
        # Make some updates to create history
        belief_update.update_policy("response_detail_level", 0.6, "Test 1")
        belief_update.update_policy("response_detail_level", 0.7, "Test 2")
        belief_update.update_policy("response_detail_level", 0.8, "Test 3")

        stability = belief_update.get_policy_stability_metrics()

        assert isinstance(stability, dict)
        assert "response_detail_level" in stability
        assert 0.0 <= stability["response_detail_level"] <= 1.0

        # Policy with no changes should have perfect stability
        assert "proactive_question_frequency" in stability
        assert stability["proactive_question_frequency"] == 1.0

    def test_rollback_policy(self, belief_update):
        """Test policy rollback functionality."""
        # Make some updates
        belief_update.update_policy("response_detail_level", 0.7, "Update 1")
        belief_update.update_policy("response_detail_level", 0.8, "Update 2")

        # Current value should be 0.8
        policy = belief_update.get_policy("response_detail_level")
        current_value = policy.current_value
        assert current_value == 0.8

        # Rollback should succeed
        success = belief_update.rollback_policy("response_detail_level", steps_back=1)
        assert success is True

        # Value should have changed from rollback
        policy = belief_update.get_policy("response_detail_level")
        assert policy.current_value != current_value

    def test_rollback_policy_insufficient_history(self, belief_update):
        """Test rollback fails when there's insufficient history."""
        success = belief_update.rollback_policy("response_detail_level", steps_back=1)
        assert success is False  # No history to rollback to
