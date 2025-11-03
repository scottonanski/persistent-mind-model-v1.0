"""
Scoring framework for Phase 3 proactive synthesis.

Provides deterministic, auditable scoring functions for:
- Hypothesis evaluation (precision/recall, lift, regret)
- Experiment outcomes (uplift, confidence intervals)
- Belief updates (bounded, deterministic deltas)
- Policy stability metrics

All scoring functions are deterministic with fixed seeds where needed.
"""

import hashlib
import math
from dataclasses import dataclass
from typing import Any


@dataclass
class HypothesisScore:
    """Deterministic scoring for hypothesis evaluation."""

    precision: float  # True positives / (true positives + false positives)
    recall: float  # True positives / (true positives + false negatives)
    lift: float  # Improvement over baseline
    confidence: float  # Statistical confidence (0-1)
    regret: float  # Opportunity cost of wrong decisions


@dataclass
class ExperimentOutcome:
    """Deterministic experiment outcome metrics."""

    arm: str
    metric_values: dict[str, float]
    uplift: float
    confidence_interval: tuple[float, float]
    sample_size: int
    statistical_significance: bool


@dataclass
class BeliefDelta:
    """Bounded, auditable belief update."""

    policy_key: str
    before_value: float
    delta: float
    after_value: float
    basis_hypothesis_id: int
    confidence: float
    timestamp: str


class DeterministicScorer:
    """
    Deterministic scoring system with fixed seeds and reproducible results.

    All scoring functions use deterministic algorithms with no randomness
    beyond what's explicitly controlled by seeds.
    """

    def __init__(self, seed: int = 42):
        """Initialize with fixed seed for reproducibility."""
        self.seed = seed
        self._hash_counter = 0

    def _deterministic_hash(self, input_data: str) -> float:
        """
        Generate deterministic float from input string.

        Used for any "random" decisions that need reproducibility.
        """
        combined = f"{self.seed}:{self._hash_counter}:{input_data}"
        hash_obj = hashlib.sha256(combined.encode())
        self._hash_counter += 1

        # Convert hash to float between 0 and 1
        hash_int = int(hash_obj.hexdigest()[:8], 16)
        return hash_int / 0xFFFFFFFF

    def score_hypothesis(
        self,
        true_positives: int,
        false_positives: int,
        true_negatives: int,
        false_negatives: int,
        baseline_performance: float = 0.5,
    ) -> HypothesisScore:
        """
        Score hypothesis with deterministic precision/recall/lift.

        Args:
            true_positives: Correct positive predictions
            false_positives: Incorrect positive predictions
            true_negatives: Correct negative predictions
            false_negatives: Incorrect negative predictions
            baseline_performance: Expected performance without hypothesis

        Returns:
            HypothesisScore with all metrics computed deterministically
        """
        # Calculate precision and recall with safe division
        precision = (
            true_positives / (true_positives + false_positives)
            if (true_positives + false_positives) > 0
            else 0.0
        )

        recall = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives) > 0
            else 0.0
        )

        # Calculate F1 score
        f1 = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        # Lift is improvement over baseline
        lift = f1 - baseline_performance if f1 > baseline_performance else 0.0

        # Confidence based on sample size (deterministic formula)
        total_samples = (
            true_positives + false_positives + true_negatives + false_negatives
        )
        confidence = (
            min(1.0, math.sqrt(total_samples / 100.0)) if total_samples > 0 else 0.0
        )

        # Regret is opportunity cost (false negatives weighted higher)
        regret = (false_negatives * 0.7 + false_positives * 0.3) / max(1, total_samples)

        return HypothesisScore(
            precision=precision,
            recall=recall,
            lift=lift,
            confidence=confidence,
            regret=regret,
        )

    def evaluate_experiment_outcome(
        self, arm_results: dict[str, list[float]], control_arm: str = "control"
    ) -> list[ExperimentOutcome]:
        """
        Evaluate A/B test results with deterministic statistics.

        Args:
            arm_results: Dictionary mapping arm names to list of metric values
            control_arm: Name of control/baseline arm

        Returns:
            List of ExperimentOutcome for each arm
        """
        outcomes = []

        # Calculate control baseline
        control_values = arm_results.get(control_arm, [])
        control_mean = (
            sum(control_values) / len(control_values) if control_values else 0.0
        )

        for arm, values in arm_results.items():
            if not values:
                continue

            arm_mean = sum(values) / len(values)

            # Calculate uplift over control
            uplift = arm_mean - control_mean if arm != control_arm else 0.0

            # Deterministic confidence interval (using fixed z-score for 95% CI)
            z_score = 1.96  # Fixed for determinism
            std_error = (
                math.sqrt(
                    sum((x - arm_mean) ** 2 for x in values)
                    / (len(values) * (len(values) - 1))
                )
                if len(values) > 1
                else 0.0
            )
            margin_error = z_score * std_error
            confidence_interval = (arm_mean - margin_error, arm_mean + margin_error)

            # Statistical significance (deterministic t-test approximation)
            if arm != control_arm and len(control_values) > 0:
                pooled_std = (
                    math.sqrt(
                        (
                            (len(values) - 1) * std_error**2
                            + (len(control_values) - 1)
                            * math.sqrt(
                                sum((x - control_mean) ** 2 for x in control_values)
                                / (len(control_values) * (len(control_values) - 1))
                            )
                            ** 2
                        )
                        / (len(values) + len(control_values) - 2)
                    )
                    if len(values) > 1 and len(control_values) > 1
                    else 0.0
                )

                t_statistic = (
                    (arm_mean - control_mean)
                    / (
                        pooled_std
                        * math.sqrt(1 / len(values) + 1 / len(control_values))
                    )
                    if pooled_std > 0
                    else 0.0
                )
                statistical_significance = abs(t_statistic) > z_score
            else:
                statistical_significance = False

            outcomes.append(
                ExperimentOutcome(
                    arm=arm,
                    metric_values={"mean": arm_mean, "std": std_error},
                    uplift=uplift,
                    confidence_interval=confidence_interval,
                    sample_size=len(values),
                    statistical_significance=statistical_significance,
                )
            )

        return outcomes

    def compute_belief_delta(
        self,
        policy_key: str,
        current_value: float,
        hypothesis_score: HypothesisScore,
        max_delta: float = 0.1,
        min_confidence: float = 0.5,
    ) -> BeliefDelta | None:
        """
        Compute bounded belief update based on hypothesis evidence.

        Args:
            policy_key: Policy parameter being updated
            current_value: Current value of the parameter
            hypothesis_score: Evidence from hypothesis testing
            max_delta: Maximum allowed change per update
            min_confidence: Minimum confidence required for update

        Returns:
            BeliefDelta if update is warranted, None otherwise
        """
        # Only update with sufficient confidence
        if hypothesis_score.confidence < min_confidence:
            return None

        # Only update if lift is positive (improvement)
        if hypothesis_score.lift <= 0:
            return None

        # Compute delta based on lift and confidence, bounded by max_delta
        raw_delta = hypothesis_score.lift * hypothesis_score.confidence * 0.5
        bounded_delta = max(-max_delta, min(max_delta, raw_delta))

        # Apply delta
        after_value = current_value + bounded_delta

        return BeliefDelta(
            policy_key=policy_key,
            before_value=current_value,
            delta=bounded_delta,
            after_value=after_value,
            basis_hypothesis_id=0,  # Will be set by caller
            confidence=hypothesis_score.confidence,
            timestamp="",  # Will be set by caller
        )

    def calculate_policy_stability(
        self,
        policy_history: list[tuple[str, float, int]],  # (policy_key, value, event_id)
        window_size: int = 100,
    ) -> dict[str, float]:
        """
        Calculate policy stability metrics over recent events.

        Args:
            policy_history: List of policy changes with event IDs
            window_size: Number of recent events to consider

        Returns:
            Dictionary mapping policy keys to stability scores (0-1, higher = more stable)
        """
        if not policy_history:
            return {}

        # Group by policy key
        policy_values = {}
        for policy_key, value, event_id in policy_history:
            if policy_key not in policy_values:
                policy_values[policy_key] = []
            policy_values[policy_key].append((event_id, value))

        stability_scores = {}

        for policy_key, values in policy_values.items():
            if len(values) < 2:
                stability_scores[policy_key] = 1.0  # No changes = perfectly stable
                continue

            # Sort by event ID and take recent window
            values.sort(key=lambda x: x[0])
            recent_values = values[-window_size:]

            # Calculate variance as instability measure
            value_list = [v for _, v in recent_values]
            mean_value = sum(value_list) / len(value_list)

            variance = sum((v - mean_value) ** 2 for v in value_list) / len(value_list)

            # Convert variance to stability (inverse relationship)
            stability = 1.0 / (1.0 + variance * 10)  # Scale factor for sensitivity
            stability_scores[policy_key] = stability

        return stability_scores

    def calculate_evidence_density(
        self, decisions: list[dict[str, Any]]  # Each decision has 'citations' list
    ) -> float:
        """
        Calculate evidence density (citations per decision).

        Args:
            decisions: List of decisions with citation evidence

        Returns:
            Evidence density score (higher = better evidenced)
        """
        if not decisions:
            return 0.0

        total_citations = sum(
            len(decision.get("citations", [])) for decision in decisions
        )
        return total_citations / len(decisions)


# Global scorer instance with fixed seed
_scorer = DeterministicScorer(seed=42)


def get_scorer() -> DeterministicScorer:
    """Get the global deterministic scorer instance."""
    return _scorer


def score_hypothesis(*args, **kwargs) -> HypothesisScore:
    """Convenience function for hypothesis scoring."""
    return _scorer.score_hypothesis(*args, **kwargs)


def evaluate_experiment(*args, **kwargs) -> list[ExperimentOutcome]:
    """Convenience function for experiment evaluation."""
    return _scorer.evaluate_experiment_outcome(*args, **kwargs)


def compute_belief_update(*args, **kwargs) -> BeliefDelta | None:
    """Convenience function for belief updates."""
    return _scorer.compute_belief_delta(*args, **kwargs)
