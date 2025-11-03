"""
Belief update system for Phase 3 hypothesis-driven learning.

Applies bounded, deterministic belief updates based on supported hypotheses
and experiment results. All updates are auditable and reversible.

Belief updates are strictly bounded and require strong evidence.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pmm.runtime.experiment_harness import ExperimentHarness, ExperimentOutcome
from pmm.runtime.hypothesis_tracker import HypothesisTracker
from pmm.runtime.scoring import BeliefDelta, get_scorer
from pmm.storage.eventlog import EventLog


@dataclass
class PolicyParameter:
    """A policy parameter that can be updated."""

    key: str
    current_value: float
    min_value: float
    max_value: float
    description: str
    last_updated: str | None
    update_history: list[tuple[float, str, str]]  # (value, timestamp, reason)


@dataclass
class BeliefUpdateBatch:
    """A batch of belief updates applied together."""

    batch_id: str
    timestamp: str
    updates: list[BeliefDelta]
    evidence_summary: dict[str, Any]
    total_delta: float  # Sum of absolute changes


class BeliefUpdate:
    """
    Bounded, auditable belief update system.

    Applies policy parameter updates based on strong evidence from
    supported hypotheses and successful experiments.
    """

    def __init__(self, eventlog: EventLog, max_delta_per_update: float = 0.1):
        self.eventlog = eventlog
        self.scorer = get_scorer()
        self.max_delta_per_update = max_delta_per_update
        self.policies: dict[str, PolicyParameter] = self._initialize_default_policies()
        self._update_history: list[BeliefUpdateBatch] = []
        self._min_evidence_confidence = 0.8  # Minimum confidence for updates
        self._min_experiment_uplift = 0.05  # Minimum uplift required

    def _initialize_default_policies(self) -> dict[str, PolicyParameter]:
        """Initialize default policy parameters with safe bounds."""
        return {
            # Communication style policies
            "response_detail_level": PolicyParameter(
                key="response_detail_level",
                current_value=0.5,
                min_value=0.1,
                max_value=1.0,
                description="Level of detail in responses (0.1=concise, 1.0=very detailed)",
                last_updated=None,
                update_history=[],
            ),
            "technical_explanation_depth": PolicyParameter(
                key="technical_explanation_depth",
                current_value=0.5,
                min_value=0.1,
                max_value=1.0,
                description="Depth of technical explanations (0.1=simple, 1.0=expert)",
                last_updated=None,
                update_history=[],
            ),
            # Engagement policies
            "proactive_question_frequency": PolicyParameter(
                key="proactive_question_frequency",
                current_value=0.3,
                min_value=0.0,
                max_value=0.8,
                description="Frequency of asking clarifying questions (0.0=never, 0.8=often)",
                last_updated=None,
                update_history=[],
            ),
            # Learning policies
            "reflection_frequency": PolicyParameter(
                key="reflection_frequency",
                current_value=0.5,
                min_value=0.1,
                max_value=1.0,
                description="Frequency of self-reflection (0.1=rare, 1.0=frequent)",
                last_updated=None,
                update_history=[],
            ),
            # Commitment policies
            "commitment_ambition": PolicyParameter(
                key="commitment_ambition",
                current_value=0.5,
                min_value=0.2,
                max_value=0.9,
                description="Ambition level of commitments (0.2=conservative, 0.9=ambitious)",
                last_updated=None,
                update_history=[],
            ),
        }

    def get_policy(self, policy_key: str) -> PolicyParameter | None:
        """Get current policy parameter."""
        return self.policies.get(policy_key)

    def update_policy(
        self,
        policy_key: str,
        new_value: float,
        reason: str,
        evidence_hypothesis_id: int | None = None,
        evidence_experiment_id: str | None = None,
    ) -> bool:
        """
        Update a policy parameter with bounds checking and audit trail.

        Args:
            policy_key: Policy parameter to update
            new_value: New value (will be bounded by policy limits)
            reason: Human-readable reason for update
            evidence_hypothesis_id: Supporting hypothesis ID
            evidence_experiment_id: Supporting experiment ID

        Returns:
            True if update applied, False otherwise
        """
        if policy_key not in self.policies:
            return False

        policy = self.policies[policy_key]
        old_value = policy.current_value

        # Apply bounds
        bounded_value = max(policy.min_value, min(policy.max_value, new_value))

        # Check if change is significant enough
        if abs(bounded_value - old_value) < 0.01:
            return False  # Change too small to log

        # Update policy
        policy.current_value = bounded_value
        policy.last_updated = datetime.now(timezone.utc).isoformat()

        # Add to history
        policy.update_history.append((bounded_value, policy.last_updated, reason))

        # Keep history manageable
        if len(policy.update_history) > 50:
            policy.update_history = policy.update_history[-25:]

        # Log update
        self.eventlog.append(
            kind="belief_update",
            content=f"Updated policy {policy_key}: {old_value:.3f} → {bounded_value:.3f} ({reason})",
            meta={
                "policy_key": policy_key,
                "old_value": old_value,
                "new_value": bounded_value,
                "delta": bounded_value - old_value,
                "reason": reason,
                "evidence_hypothesis_id": evidence_hypothesis_id,
                "evidence_experiment_id": evidence_experiment_id,
                "timestamp": policy.last_updated,
            },
        )

        return True

    def compute_updates_from_evidence(
        self,
        hypothesis_tracker: HypothesisTracker,
        experiment_harness: ExperimentHarness,
    ) -> list[BeliefDelta]:
        """
        Compute belief updates based on current evidence.

        Args:
            hypothesis_tracker: Source of hypothesis evidence
            experiment_harness: Source of experiment evidence

        Returns:
            List of proposed belief deltas
        """
        updates = []

        # Get supported hypotheses
        supported_hypotheses = hypothesis_tracker.get_supported_hypotheses()

        for hypothesis in supported_hypotheses:
            # Get hypothesis score
            hypothesis_score = hypothesis_tracker.get_hypothesis_score(hypothesis.id)

            if not hypothesis_score:
                continue

            # Check if hypothesis meets confidence threshold
            if hypothesis_score.confidence < self._min_evidence_confidence:
                continue

            # Map hypothesis to policy updates
            policy_updates = self._map_hypothesis_to_policies(
                hypothesis, hypothesis_score
            )
            updates.extend(policy_updates)

        # Check experiment results
        for experiment_state in experiment_harness.get_active_experiments():
            if experiment_state.status != "completed":
                continue

            results = experiment_harness.get_experiment_results(
                experiment_state.config.experiment_id
            )

            if not results:
                continue

            # Find significant uplifts
            for result in results:
                if result.arm != "control" and result.statistical_significance:
                    if result.uplift >= self._min_experiment_uplift:
                        policy_updates = self._map_experiment_to_policies(
                            experiment_state, result
                        )
                        updates.extend(policy_updates)

        # Deduplicate and prioritize updates
        return self._prioritize_updates(updates)

    def _map_hypothesis_to_policies(
        self, hypothesis, hypothesis_score
    ) -> list[BeliefDelta]:
        """Map hypothesis content to relevant policy updates."""
        updates = []
        hypothesis_text = hypothesis.statement.lower()

        # Simple heuristic mapping based on hypothesis content
        if "communication" in hypothesis_text or "response" in hypothesis_text:
            if "detailed" in hypothesis_text or "comprehensive" in hypothesis_text:
                delta = self.scorer.compute_belief_delta(
                    policy_key="response_detail_level",
                    current_value=self.policies["response_detail_level"].current_value,
                    hypothesis_score=hypothesis_score,
                    max_delta=self.max_delta_per_update,
                )
                if delta:
                    delta.basis_hypothesis_id = hypothesis.id
                    updates.append(delta)

        if "technical" in hypothesis_text or "explanation" in hypothesis_text:
            delta = self.scorer.compute_belief_delta(
                policy_key="technical_explanation_depth",
                current_value=self.policies[
                    "technical_explanation_depth"
                ].current_value,
                hypothesis_score=hypothesis_score,
                max_delta=self.max_delta_per_update,
            )
            if delta:
                delta.basis_hypothesis_id = hypothesis.id
                updates.append(delta)

        if "question" in hypothesis_text or "clarify" in hypothesis_text:
            delta = self.scorer.compute_belief_delta(
                policy_key="proactive_question_frequency",
                current_value=self.policies[
                    "proactive_question_frequency"
                ].current_value,
                hypothesis_score=hypothesis_score,
                max_delta=self.max_delta_per_update,
            )
            if delta:
                delta.basis_hypothesis_id = hypothesis.id
                updates.append(delta)

        if "reflection" in hypothesis_text or "learning" in hypothesis_text:
            delta = self.scorer.compute_belief_delta(
                policy_key="reflection_frequency",
                current_value=self.policies["reflection_frequency"].current_value,
                hypothesis_score=hypothesis_score,
                max_delta=self.max_delta_per_update,
            )
            if delta:
                delta.basis_hypothesis_id = hypothesis.id
                updates.append(delta)

        if "commitment" in hypothesis_text or "goal" in hypothesis_text:
            delta = self.scorer.compute_belief_delta(
                policy_key="commitment_ambition",
                current_value=self.policies["commitment_ambition"].current_value,
                hypothesis_score=hypothesis_score,
                max_delta=self.max_delta_per_update,
            )
            if delta:
                delta.basis_hypothesis_id = hypothesis.id
                updates.append(delta)

        return updates

    def _map_experiment_to_policies(
        self, experiment_state, result: ExperimentOutcome
    ) -> list[BeliefDelta]:
        """Map experiment results to relevant policy updates."""
        updates = []
        experiment_text = experiment_state.config.description.lower()

        # Create a mock hypothesis score for experiment-based updates
        from pmm.runtime.scoring import HypothesisScore

        mock_score = HypothesisScore(
            precision=0.8,
            recall=0.8,
            lift=result.uplift,
            confidence=0.9,  # High confidence for successful experiments
            regret=0.1,
        )

        # Map based on experiment description and result
        if "communication" in experiment_text:
            delta = self.scorer.compute_belief_delta(
                policy_key="response_detail_level",
                current_value=self.policies["response_detail_level"].current_value,
                hypothesis_score=mock_score,
                max_delta=self.max_delta_per_update,
            )
            if delta:
                updates.append(delta)

        if "technical" in experiment_text:
            delta = self.scorer.compute_belief_delta(
                policy_key="technical_explanation_depth",
                current_value=self.policies[
                    "technical_explanation_depth"
                ].current_value,
                hypothesis_score=mock_score,
                max_delta=self.max_delta_per_update,
            )
            if delta:
                updates.append(delta)

        return updates

    def _prioritize_updates(self, updates: list[BeliefDelta]) -> list[BeliefDelta]:
        """Prioritize and deduplicate belief updates."""
        if not updates:
            return []

        # Group by policy key
        policy_updates = {}
        for update in updates:
            if update.policy_key not in policy_updates:
                policy_updates[update.policy_key] = []
            policy_updates[update.policy_key].append(update)

        # For each policy, select the update with highest confidence
        prioritized = []
        for policy_key, policy_update_list in policy_updates.items():
            # Sort by confidence, then by lift magnitude
            best_update = max(
                policy_update_list, key=lambda u: (u.confidence, abs(u.delta))
            )
            prioritized.append(best_update)

        # Sort overall by confidence
        prioritized.sort(key=lambda u: u.confidence, reverse=True)

        return prioritized

    def apply_belief_updates(
        self, updates: list[BeliefDelta], batch_reason: str = "Scheduled belief update"
    ) -> BeliefUpdateBatch:
        """
        Apply a batch of belief updates atomically.

        Args:
            updates: List of belief deltas to apply
            batch_reason: Reason for this batch of updates

        Returns:
            BeliefUpdateBatch with applied updates
        """
        batch_id = f"batch_{int(time.time())}"
        timestamp = datetime.now(timezone.utc).isoformat()

        applied_updates = []
        total_delta = 0.0

        for update in updates:
            # Set timestamp on update
            update.timestamp = timestamp

            # Apply the update
            success = self.update_policy(
                policy_key=update.policy_key,
                new_value=update.after_value,
                reason=f"{batch_reason} (hypothesis {update.basis_hypothesis_id})",
                evidence_hypothesis_id=update.basis_hypothesis_id,
            )

            if success:
                applied_updates.append(update)
                total_delta += abs(update.delta)

        # Create batch record
        batch = BeliefUpdateBatch(
            batch_id=batch_id,
            timestamp=timestamp,
            updates=applied_updates,
            evidence_summary={
                "total_updates": len(applied_updates),
                "total_delta": total_delta,
                "source_hypotheses": list(
                    set(u.basis_hypothesis_id for u in applied_updates)
                ),
            },
            total_delta=total_delta,
        )

        # Log batch
        self.eventlog.append(
            kind="belief_update_batch",
            content=(
                f"Applied belief update batch {batch_id}: {len(applied_updates)} updates, "
                f"total delta {total_delta:.3f}"
            ),
            meta={
                "batch_id": batch_id,
                "batch_reason": batch_reason,
                "applied_updates": len(applied_updates),
                "total_delta": total_delta,
                "evidence_summary": batch.evidence_summary,
            },
        )

        # Store in history
        self._update_history.append(batch)

        # Keep history manageable
        if len(self._update_history) > 100:
            self._update_history = self._update_history[-50:]

        return batch

    def get_policy_stability_metrics(self) -> dict[str, float]:
        """Calculate stability metrics for all policies."""
        stability_metrics = {}

        for policy_key, policy in self.policies.items():
            if len(policy.update_history) < 2:
                stability_metrics[policy_key] = 1.0  # Perfectly stable (no changes)
                continue

            # Calculate recent volatility
            recent_values = [update[0] for update in policy.update_history[-10:]]
            mean_value = sum(recent_values) / len(recent_values)

            variance = sum((v - mean_value) ** 2 for v in recent_values) / len(
                recent_values
            )
            stability = 1.0 / (1.0 + variance * 10)  # Convert to stability score

            stability_metrics[policy_key] = stability

        return stability_metrics

    def get_current_policies(self) -> dict[str, float]:
        """Get current values for all policies."""
        return {key: policy.current_value for key, policy in self.policies.items()}

    def rollback_policy(self, policy_key: str, steps_back: int = 1) -> bool:
        """
        Rollback a policy to a previous value.

        Args:
            policy_key: Policy to rollback
            steps_back: Number of steps to rollback (1 = previous value)

        Returns:
            True if rollback successful, False otherwise
        """
        if policy_key not in self.policies:
            return False

        policy = self.policies[policy_key]

        if len(policy.update_history) < steps_back:
            return False

        # Get the target value
        target_index = -(steps_back + 1)
        if target_index < -len(policy.update_history):
            target_value = policy.update_history[0][0]  # Original value
        else:
            target_value = policy.update_history[target_index][0]

        # Apply rollback
        return self.update_policy(
            policy_key=policy_key,
            new_value=target_value,
            reason=f"Rollback {steps_back} steps",
        )
