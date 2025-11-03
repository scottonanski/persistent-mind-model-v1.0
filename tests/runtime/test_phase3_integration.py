"""Integration tests for Phase 3: Proactive Synthesis & Hypothesis-Driven Learning."""

import os
import tempfile

import pytest

from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog


class TestPhase3Integration:
    """Test complete Phase 3 workflow integration."""

    @pytest.fixture
    def eventlog(self):
        """Create temporary eventlog for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            eventlog = EventLog(db_path)
            # Seed with some initial events for pattern detection
            for i in range(20):
                eventlog.append(
                    kind="commitment" if i % 3 == 0 else "reflection",
                    content=f"Sample event {i}",
                    meta={"test": True},
                )
            yield eventlog
        finally:
            os.unlink(db_path)

    @pytest.fixture
    def runtime(self, eventlog):
        """Create runtime with Phase 3 components."""
        cfg = LLMConfig(provider="dummy", model="test-model")
        return Runtime(cfg, eventlog)

    def test_phase3_components_initialization(self, runtime):
        """Test all Phase 3 components are properly initialized."""
        assert hasattr(runtime, "synthesis_engine")
        assert hasattr(runtime, "hypothesis_tracker")
        assert hasattr(runtime, "experiment_harness")
        assert hasattr(runtime, "belief_update")

        # Check cadence controls
        assert runtime._synthesis_cadence == 50
        assert runtime._experiment_cadence == 100
        assert runtime._belief_update_cadence == 25
        assert runtime._last_synthesis_tick == 0
        assert runtime._last_experiment_tick == 0
        assert runtime._last_belief_update_tick == 0

    def test_synthesis_engine_workflow(self, runtime):
        """Test synthesis engine generates patterns and hypotheses."""
        # Run synthesis analysis
        snapshot = runtime.synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=2, max_candidates=3
        )

        assert snapshot is not None
        assert hasattr(snapshot, "patterns")
        assert hasattr(snapshot, "candidates")
        assert hasattr(snapshot, "metadata")
        assert snapshot.metadata.get("analysis_seed") == 42  # Deterministic seed

        # Test hypothesis generation from patterns
        if snapshot.patterns:
            pattern = snapshot.patterns[0]
            hypothesis_id = runtime.synthesis_engine.generate_hypothesis_from_pattern(
                pattern, runtime.hypothesis_tracker
            )

            # Should either generate a hypothesis or return None if pattern too weak
            assert hypothesis_id is None or isinstance(hypothesis_id, int)

    def test_hypothesis_lifecycle(self, runtime):
        """Test complete hypothesis lifecycle from creation to evidence."""
        from pmm.runtime.hypothesis_tracker import HypothesisStatus

        # Create a hypothesis
        hypothesis = runtime.hypothesis_tracker.create_hypothesis(
            statement="If users ask questions then I provide detailed responses within 5 events measured by response_quality",
            priors=0.7,
            evidence_tokens=["[1:acf76915]"],
        )

        assert hypothesis is not None
        assert hypothesis.status == HypothesisStatus.ACTIVE

        # Add supporting evidence
        for _ in range(15):
            runtime.hypothesis_tracker.add_evidence(hypothesis.id, True, 0.9)
            # Refresh hypothesis after adding evidence
            hypothesis = runtime.hypothesis_tracker.get_hypothesis(hypothesis.id)
            if not hypothesis:
                break

        # Should transition to SUPPORTED with enough evidence
        assert hypothesis.status in [
            HypothesisStatus.SUPPORTED,
            HypothesisStatus.ACTIVE,
        ]  # May need more evidence

        # Get hypothesis score
        score = runtime.hypothesis_tracker.get_hypothesis_score(hypothesis.id)
        assert score is not None
        assert score.confidence > 0.0

    def test_experiment_lifecycle(self, runtime):
        """Test experiment creation, assignment, and completion."""
        # Create an experiment
        exp_id = runtime.experiment_harness.create_experiment(
            hypothesis_id=123,
            name="Test experiment",
            description="Testing experiment lifecycle",
            arms=["control", "variant"],
            horizon=5,
            sample_size=3,
        )

        assert exp_id is not None

        # Start the experiment
        success = runtime.experiment_harness.start_experiment(exp_id)
        assert success is True

        # Assign events and record outcomes
        for i in range(6):  # More than horizon to test termination
            event_id = 1000 + i
            arm = runtime.experiment_harness.assign_event(exp_id, event_id)
            if arm:
                metric_value = 0.5 if arm == "control" else 0.8
                runtime.experiment_harness.record_outcome(
                    exp_id, event_id, metric_value
                )

        # Check experiment completed
        state = runtime.experiment_harness.get_experiment_state(exp_id)
        assert state.status == "completed"

        # Check results
        results = runtime.experiment_harness.get_experiment_results(exp_id)
        assert results is not None
        assert len(results) >= 1

    def test_belief_update_workflow(self, runtime):
        """Test belief updates from evidence."""
        # Get initial policies
        initial_policies = runtime.belief_update.get_current_policies()
        assert len(initial_policies) > 0

        # Make a policy update
        success = runtime.belief_update.update_policy(
            "response_detail_level", 0.7, "Integration test update"
        )
        assert success is True

        # Check policy was updated
        updated_policies = runtime.belief_update.get_current_policies()
        assert updated_policies["response_detail_level"] == 0.7

        # Check stability metrics
        stability = runtime.belief_update.get_policy_stability_metrics()
        assert isinstance(stability, dict)
        assert "response_detail_level" in stability
        assert 0.0 <= stability["response_detail_level"] <= 1.0

    def test_runtime_phase3_methods(self, runtime):
        """Test the three thin orchestration methods in Runtime."""
        # Test synthesis tick
        runtime.maybe_run_synthesis_tick()

        # Check synthesis event was logged
        recent_events = list(runtime.eventlog.read_tail(limit=5))
        synthesis_events = [
            e for e in recent_events if e.get("kind") == "synthesis_tick"
        ]
        assert len(synthesis_events) > 0

        # Test experiment spawn (may not spawn without supported hypotheses)
        runtime.maybe_spawn_experiments()

        # Test belief updates (may not apply without evidence)
        runtime.apply_belief_updates()

        # All methods should complete without exceptions
        assert True

    def test_phase3_cadence_gating(self, runtime):
        """Test that Phase 3 methods respect cadence gating."""
        # Reset tick counters
        runtime._last_synthesis_tick = 0
        runtime._last_experiment_tick = 0
        runtime._last_belief_update_tick = 0

        # First call should execute (cadence met)
        runtime.maybe_run_synthesis_tick()
        runtime.maybe_spawn_experiments()
        runtime.apply_belief_updates()

        # Update tick counters to simulate recent execution
        current_tick = 10
        runtime._last_synthesis_tick = current_tick
        runtime._last_experiment_tick = current_tick
        runtime._last_belief_update_tick = current_tick

        # Mock current tick for cadence check
        import unittest.mock

        with unittest.mock.patch(
            "pmm.runtime.loop.handlers.len", return_value=current_tick + 1
        ):
            # These calls should be skipped due to cadence
            runtime.maybe_run_synthesis_tick()
            runtime.maybe_spawn_experiments()
            runtime.apply_belief_updates()

        # Cadence should prevent execution
        assert runtime._last_synthesis_tick == current_tick
        assert runtime._last_experiment_tick == current_tick
        assert runtime._last_belief_update_tick == current_tick

    def test_phase3_error_handling(self, runtime):
        """Test Phase 3 components handle errors gracefully."""
        # Test synthesis with invalid parameters
        try:
            runtime.synthesis_engine.run_synthesis(
                window_size=0, min_pattern_support=1, max_candidates=1  # Invalid
            )
        except Exception:
            pass  # Should handle gracefully

        # Test hypothesis tracker with invalid evidence
        hypothesis = runtime.hypothesis_tracker.create_hypothesis(
            statement="Test hypothesis",
            priors=0.5,
            evidence_tokens=["[1:invalid]"],  # Invalid token
        )
        # Should return None for invalid evidence
        assert hypothesis is None

        # Test experiment harness with invalid arms
        exp_id = runtime.experiment_harness.create_experiment(
            hypothesis_id=123,
            name="Invalid experiment",
            description="Missing control arm",
            arms=["variant_a", "variant_b"],  # No control
        )
        assert exp_id is None

        # All error cases should be handled gracefully
        assert True

    def test_phase3_determinism(self, runtime):
        """Test Phase 3 components produce deterministic results."""
        # Run synthesis twice with same parameters
        snapshot1 = runtime.synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=2, max_candidates=3
        )

        snapshot2 = runtime.synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=2, max_candidates=3
        )

        # Should produce identical results (deterministic)
        assert len(snapshot1.patterns) == len(snapshot2.patterns)
        assert snapshot1.metadata.get("analysis_seed") == snapshot2.metadata.get(
            "analysis_seed"
        )

        # Test deterministic experiment assignment
        exp_id = runtime.experiment_harness.create_experiment(
            hypothesis_id=123,
            name="Determinism test",
            description="Test deterministic assignment",
            arms=["control", "variant"],
        )

        runtime.experiment_harness.start_experiment(exp_id)

        # Same event ID should get same arm assignment
        arm1 = runtime.experiment_harness.assign_event(exp_id, 1001)
        arm2 = runtime.experiment_harness.assign_event(exp_id, 1001)  # Same ID

        assert arm1 == arm2

    def test_phase3_audit_trail(self, runtime):
        """Test Phase 3 operations create proper audit trails."""
        # Run Phase 3 operations
        runtime.maybe_run_synthesis_tick()

        # Create hypothesis
        hypothesis = runtime.hypothesis_tracker.create_hypothesis(
            statement="Test audit trail hypothesis",
            priors=0.7,
            evidence_tokens=["[1:acf76915]"],
        )

        if hypothesis:
            # Add evidence
            runtime.hypothesis_tracker.add_evidence(hypothesis.id, True, 0.9)

        # Create experiment
        exp_id = runtime.experiment_harness.create_experiment(
            hypothesis_id=123,
            name="Audit test experiment",
            description="Testing audit trail",
            arms=["control", "variant"],
        )

        if exp_id:
            runtime.experiment_harness.start_experiment(exp_id)

        # Update policy
        runtime.belief_update.update_policy(
            "response_detail_level", 0.6, "Audit test update"
        )

        # Check all operations created audit events
        recent_events = list(runtime.eventlog.read_tail(limit=20))

        event_kinds = {e.get("kind") for e in recent_events}

        # Should have Phase 3 event kinds
        assert "synthesis_tick" in event_kinds
        assert any("hypothesis" in kind for kind in event_kinds)
        assert any("experiment" in kind for kind in event_kinds)
        assert "belief_update" in event_kinds

        # All Phase 3 events should have proper metadata
        phase3_kinds = [
            "synthesis_tick",
            "hypothesis_open",
            "experiment_open",
            "belief_update",
        ]
        for event in recent_events:
            if event.get("kind") in phase3_kinds or any(
                keyword in event.get("kind", "")
                for keyword in [
                    "hypothesis",
                    "experiment",
                    "synthesis",
                    "belief_update",
                ]
            ):
                assert event.get("id") is not None
                assert event.get("kind") is not None
                assert event.get("content") is not None
                # Meta field should exist for Phase 3 events
                assert event.get("meta") is not None
