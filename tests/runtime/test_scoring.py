"""Tests for Phase 3 scoring framework."""

from pmm.runtime.scoring import (
    BeliefDelta,
    DeterministicScorer,
    ExperimentOutcome,
    HypothesisScore,
    compute_belief_update,
    evaluate_experiment,
    score_hypothesis,
)


class TestDeterministicScorer:
    """Test deterministic scoring functions."""

    def test_scorer_determinism(self):
        """Test that scorer produces consistent results."""
        scorer1 = DeterministicScorer(seed=42)
        scorer2 = DeterministicScorer(seed=42)

        # Same inputs should produce same outputs
        score1 = scorer1.score_hypothesis(10, 2, 8, 1)
        score2 = scorer2.score_hypothesis(10, 2, 8, 1)

        assert score1.precision == score2.precision
        assert score1.recall == score2.recall
        assert score1.lift == score2.lift
        assert score1.confidence == score2.confidence
        assert score1.regret == score2.regret

    def test_hypothesis_scoring_basic(self):
        """Test basic hypothesis scoring calculations."""
        scorer = DeterministicScorer(seed=42)

        # Perfect prediction
        score = scorer.score_hypothesis(
            true_positives=10, false_positives=0, true_negatives=10, false_negatives=0
        )

        assert score.precision == 1.0
        assert score.recall == 1.0
        assert score.lift > 0.0
        assert score.confidence > 0.0
        assert score.regret == 0.0

    def test_hypothesis_scoring_zero_division(self):
        """Test scoring handles edge cases gracefully."""
        scorer = DeterministicScorer(seed=42)

        # No positive predictions
        score = scorer.score_hypothesis(
            true_positives=0, false_positives=0, true_negatives=10, false_negatives=10
        )

        assert score.precision == 0.0
        assert score.recall == 0.0
        assert score.lift == 0.0  # No improvement over baseline

    def test_experiment_evaluation(self):
        """Test A/B experiment evaluation."""
        scorer = DeterministicScorer(seed=42)

        arm_results = {
            "control": [1.0, 1.1, 0.9, 1.2, 1.0],
            "variant_a": [1.3, 1.4, 1.2, 1.5, 1.3],
        }

        outcomes = scorer.evaluate_experiment_outcome(
            arm_results, control_arm="control"
        )

        assert len(outcomes) == 2

        # Find variant outcome
        variant_outcome = next(o for o in outcomes if o.arm == "variant_a")
        assert variant_outcome.uplift > 0.0  # Should show improvement
        assert variant_outcome.sample_size == 5
        assert len(variant_outcome.confidence_interval) == 2

    def test_belief_delta_computation(self):
        """Test belief delta calculation with bounds."""
        scorer = DeterministicScorer(seed=42)

        hypothesis_score = HypothesisScore(
            precision=0.8, recall=0.7, lift=0.2, confidence=0.8, regret=0.1
        )

        delta = scorer.compute_belief_delta(
            policy_key="test_param",
            current_value=0.5,
            hypothesis_score=hypothesis_score,
            max_delta=0.1,
        )

        assert delta is not None
        assert delta.policy_key == "test_param"
        assert delta.before_value == 0.5
        assert delta.after_value > delta.before_value  # Should increase
        assert abs(delta.delta) <= 0.1  # Should respect max_delta
        assert delta.confidence == 0.8

    def test_belief_delta_insufficient_confidence(self):
        """Test belief delta rejected for low confidence."""
        scorer = DeterministicScorer(seed=42)

        hypothesis_score = HypothesisScore(
            precision=0.6,
            recall=0.5,
            lift=0.1,
            confidence=0.3,  # Low confidence
            regret=0.2,
        )

        delta = scorer.compute_belief_delta(
            policy_key="test_param",
            current_value=0.5,
            hypothesis_score=hypothesis_score,
            min_confidence=0.5,
        )

        assert delta is None  # Should be rejected

    def test_belief_delta_no_lift(self):
        """Test belief delta rejected for no lift."""
        scorer = DeterministicScorer(seed=42)

        hypothesis_score = HypothesisScore(
            precision=0.5,
            recall=0.5,
            lift=0.0,  # No improvement
            confidence=0.8,
            regret=0.1,
        )

        delta = scorer.compute_belief_delta(
            policy_key="test_param",
            current_value=0.5,
            hypothesis_score=hypothesis_score,
        )

        assert delta is None  # Should be rejected

    def test_policy_stability_calculation(self):
        """Test policy stability metrics."""
        scorer = DeterministicScorer(seed=42)

        policy_history = [
            ("param1", 0.5, 100),
            ("param1", 0.6, 200),
            ("param1", 0.55, 300),
            ("param2", 1.0, 150),
            ("param2", 1.0, 250),  # No change = high stability
        ]

        stability = scorer.calculate_policy_stability(policy_history, window_size=100)

        assert "param1" in stability
        assert "param2" in stability
        assert stability["param2"] > stability["param1"]  # param2 more stable
        assert all(0.0 <= s <= 1.0 for s in stability.values())

    def test_evidence_density_calculation(self):
        """Test evidence density metrics."""
        scorer = DeterministicScorer(seed=42)

        decisions = [
            {"citations": ["[1:abcd1234]", "[2:efgh5678]"]},
            {"citations": ["[3:ijkl9012]"]},
            {"citations": []},  # No evidence
        ]

        density = scorer.calculate_evidence_density(decisions)

        assert density == 1.0  # (2 + 1 + 0) / 3 = 1.0

    def test_global_scorer_functions(self):
        """Test convenience functions use global scorer."""
        # These should work without errors
        score = score_hypothesis(5, 1, 4, 1)
        assert isinstance(score, HypothesisScore)

        outcomes = evaluate_experiment({"control": [1.0, 1.1], "variant": [1.2, 1.3]})
        assert len(outcomes) == 2
        assert all(isinstance(o, ExperimentOutcome) for o in outcomes)

        delta = compute_belief_update(
            "test", 0.5, HypothesisScore(0.8, 0.7, 0.2, 0.8, 0.1)
        )
        assert isinstance(delta, BeliefDelta)

    def test_deterministic_hash_consistency(self):
        """Test deterministic hash produces consistent values."""
        scorer = DeterministicScorer(seed=42)

        # Reset counter to get same sequence
        scorer._hash_counter = 0
        hash1 = scorer._deterministic_hash("test")

        scorer._hash_counter = 0
        hash2 = scorer._deterministic_hash("test")

        assert hash1 == hash2

        # Different inputs should produce different hashes
        scorer._hash_counter = 0
        hash3 = scorer._deterministic_hash("different")
        assert hash1 != hash3
