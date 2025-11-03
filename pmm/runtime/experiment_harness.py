"""
Experiment harness for Phase 3 hypothesis-driven learning.

Runs safe, bounded micro-experiments to test hypotheses with deterministic
assignment and controlled exposure.

All experiments are deterministic with fixed seeds and bounded impact.
"""

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pmm.runtime.scoring import ExperimentOutcome, get_scorer
from pmm.storage.eventlog import EventLog


@dataclass
class ExperimentConfig:
    """Configuration for a micro-experiment."""

    experiment_id: str
    hypothesis_id: int
    name: str
    description: str
    arms: list[str]  # ["control", "variant_a", "variant_b"]
    traffic_split: list[float]  # [0.7, 0.2, 0.1] must sum to 1.0
    metric: str  # What to measure
    horizon: int  # Maximum events before auto-terminate
    sample_size: int  # Maximum samples per arm
    created_at: str


@dataclass
class ExperimentState:
    """Current state of an experiment."""

    config: ExperimentConfig
    status: str  # "pending", "running", "completed", "terminated"
    started_at: str | None
    completed_at: str | None
    current_samples: dict[str, int]  # arm -> sample count
    outcomes: dict[str, list[float]]  # arm -> metric values
    assignments: dict[str, list[int]]  # arm -> event IDs assigned


class ExperimentHarness:
    """
    Safe, deterministic experiment execution system.

    Runs micro-experiments with bounded exposure, deterministic assignment,
    and automatic termination conditions.
    """

    def __init__(self, eventlog: EventLog, seed: int = 42):
        self.eventlog = eventlog
        self.seed = seed
        self.scorer = get_scorer()
        self._active_experiments: dict[str, ExperimentState] = {}
        self._max_concurrent = 2  # Safety limit
        self._max_horizon = 50  # Maximum events per experiment
        self._max_sample_size = 20  # Maximum samples per arm

    def _deterministic_assignment(self, experiment_id: str, event_id: int) -> str:
        """
        Deterministically assign an event to an experiment arm.

        Args:
            experiment_id: Unique experiment identifier
            event_id: Event ID to assign

        Returns:
            Arm name assignment
        """
        # Create deterministic hash from experiment_id, event_id, and seed
        input_data = f"{self.seed}:{experiment_id}:{event_id}"
        hash_obj = hashlib.sha256(input_data.encode())
        hash_int = int(hash_obj.hexdigest()[:8], 16)
        hash_float = hash_int / 0xFFFFFFFF

        # Find arm based on traffic split
        cumulative = 0.0
        for arm, split in zip(
            self._active_experiments[experiment_id].config.arms,
            self._active_experiments[experiment_id].config.traffic_split,
        ):
            cumulative += split
            if hash_float <= cumulative:
                return arm

        # Fallback to last arm
        return self._active_experiments[experiment_id].config.arms[-1]

    def create_experiment(
        self,
        hypothesis_id: int,
        name: str,
        description: str,
        arms: list[str],
        traffic_split: list[float] | None = None,
        metric: str = "user_satisfaction",
        horizon: int | None = None,
        sample_size: int | None = None,
    ) -> str | None:
        """
        Create a new micro-experiment with safety validation.

        Args:
            hypothesis_id: ID of hypothesis being tested
            name: Human-readable experiment name
            description: What the experiment tests
            arms: List of experiment arms (must include "control")
            traffic_split: Traffic allocation (defaults to equal split)
            metric: Primary metric for evaluation
            horizon: Maximum events before termination
            sample_size: Maximum samples per arm

        Returns:
            Experiment ID if created successfully, None otherwise
        """
        # Safety checks
        if len(self._active_experiments) >= self._max_concurrent:
            return None

        if "control" not in arms:
            return None

        if len(arms) < 2:
            return None

        # Set defaults with safety bounds
        if traffic_split is None:
            traffic_split = [1.0 / len(arms)] * len(arms)

        if abs(sum(traffic_split) - 1.0) > 0.001:
            return None  # Traffic split must sum to ~1.0

        horizon = min(horizon or self._max_horizon, self._max_horizon)
        sample_size = min(sample_size or self._max_sample_size, self._max_sample_size)

        # Create experiment config
        experiment_id = f"exp_{int(time.time())}_{hypothesis_id}"
        timestamp = datetime.now(timezone.utc).isoformat()

        config = ExperimentConfig(
            experiment_id=experiment_id,
            hypothesis_id=hypothesis_id,
            name=name,
            description=description,
            arms=arms,
            traffic_split=traffic_split,
            metric=metric,
            horizon=horizon,
            sample_size=sample_size,
            created_at=timestamp,
        )

        # Initialize experiment state
        state = ExperimentState(
            config=config,
            status="pending",
            started_at=None,
            completed_at=None,
            current_samples={arm: 0 for arm in arms},
            outcomes={arm: [] for arm in arms},
            assignments={arm: [] for arm in arms},
        )

        # Log experiment creation
        self.eventlog.append(
            kind="experiment_open",
            content=f"Created experiment {experiment_id}: {name}",
            meta={
                "experiment_id": experiment_id,
                "hypothesis_id": hypothesis_id,
                "config": {
                    "arms": arms,
                    "traffic_split": traffic_split,
                    "metric": metric,
                    "horizon": horizon,
                    "sample_size": sample_size,
                },
            },
        )

        self._active_experiments[experiment_id] = state
        return experiment_id

    def start_experiment(self, experiment_id: str) -> bool:
        """
        Start a pending experiment.

        Args:
            experiment_id: ID of experiment to start

        Returns:
            True if started successfully, False otherwise
        """
        if experiment_id not in self._active_experiments:
            return False

        state = self._active_experiments[experiment_id]

        if state.status != "pending":
            return False

        state.status = "running"
        state.started_at = datetime.now(timezone.utc).isoformat()

        # Log experiment start
        self.eventlog.append(
            kind="experiment_start",
            content=f"Started experiment {experiment_id}",
            meta={"experiment_id": experiment_id, "started_at": state.started_at},
        )

        return True

    def assign_event(self, experiment_id: str, event_id: int) -> str | None:
        """
        Assign an event to an experiment arm.

        Args:
            experiment_id: ID of running experiment
            event_id: Event ID to assign

        Returns:
            Assigned arm name, or None if assignment failed
        """
        if experiment_id not in self._active_experiments:
            return None

        state = self._active_experiments[experiment_id]

        if state.status != "running":
            return None

        # Check termination conditions
        if self._should_terminate(state):
            self._complete_experiment(experiment_id, "horizon_reached")
            return None

        # Deterministic assignment
        arm = self._deterministic_assignment(experiment_id, event_id)

        # Check arm sample limits
        if state.current_samples[arm] >= state.config.sample_size:
            # Try other arms
            for other_arm in state.config.arms:
                if state.current_samples[other_arm] < state.config.sample_size:
                    arm = other_arm
                    break
            else:
                # All arms at limit, terminate experiment
                self._complete_experiment(experiment_id, "sample_limit_reached")
                return None

        # Record assignment
        state.current_samples[arm] += 1
        state.assignments[arm].append(event_id)

        # Log assignment
        self.eventlog.append(
            kind="experiment_assignment",
            content=f"Assigned event {event_id} to {arm} in {experiment_id}",
            meta={
                "experiment_id": experiment_id,
                "event_id": event_id,
                "arm": arm,
                "current_samples": state.current_samples[arm],
            },
        )

        return arm

    def record_outcome(
        self, experiment_id: str, event_id: int, metric_value: float
    ) -> bool:
        """
        Record outcome metric for an assigned event.

        Args:
            experiment_id: ID of experiment
            event_id: Event ID that was assigned
            metric_value: Measured metric value

        Returns:
            True if recorded successfully, False otherwise
        """
        if experiment_id not in self._active_experiments:
            return False

        state = self._active_experiments[experiment_id]

        # Find which arm this event was assigned to
        assigned_arm = None
        for arm, assigned_events in state.assignments.items():
            if event_id in assigned_events:
                assigned_arm = arm
                break

        if assigned_arm is None:
            return False

        # Record outcome
        state.outcomes[assigned_arm].append(metric_value)

        # Log outcome
        self.eventlog.append(
            kind="experiment_outcome",
            content=f"Recorded outcome {metric_value} for event {event_id} in {experiment_id}",
            meta={
                "experiment_id": experiment_id,
                "event_id": event_id,
                "arm": assigned_arm,
                "metric_value": metric_value,
            },
        )

        # Check if experiment should complete
        if self._should_terminate(state):
            self._complete_experiment(experiment_id, "completed")

        return True

    def get_experiment_results(
        self, experiment_id: str
    ) -> list[ExperimentOutcome] | None:
        """
        Get current experiment results with statistical analysis.

        Args:
            experiment_id: ID of experiment

        Returns:
            List of ExperimentOutcome for each arm, or None if experiment not found
        """
        if experiment_id not in self._active_experiments:
            return None

        state = self._active_experiments[experiment_id]

        # Use scorer to evaluate outcomes
        return self.scorer.evaluate_experiment_outcome(
            state.outcomes, control_arm="control"
        )

    def _should_terminate(self, state: ExperimentState) -> bool:
        """Check if experiment should terminate based on conditions."""
        # Total sample limit
        total_samples = sum(state.current_samples.values())
        if total_samples >= state.config.horizon:
            return True

        # All arms at sample limit
        if all(
            count >= state.config.sample_size
            for count in state.current_samples.values()
        ):
            return True

        return False

    def _complete_experiment(self, experiment_id: str, reason: str) -> None:
        """Complete an experiment and log results."""
        if experiment_id not in self._active_experiments:
            return

        state = self._active_experiments[experiment_id]
        state.status = "completed"
        state.completed_at = datetime.now(timezone.utc).isoformat()

        # Get final results
        results = self.get_experiment_results(experiment_id)

        # Log completion with results
        self.eventlog.append(
            kind="experiment_complete",
            content=f"Completed experiment {experiment_id}: {reason}",
            meta={
                "experiment_id": experiment_id,
                "completion_reason": reason,
                "completed_at": state.completed_at,
                "final_samples": state.current_samples,
                "results": [
                    {
                        "arm": r.arm,
                        "uplift": r.uplift,
                        "confidence_interval": r.confidence_interval,
                        "statistical_significance": r.statistical_significance,
                    }
                    for r in (results or [])
                ],
            },
        )

    def terminate_experiment(self, experiment_id: str, reason: str = "manual") -> bool:
        """
        Manually terminate an experiment.

        Args:
            experiment_id: ID of experiment to terminate
            reason: Reason for termination

        Returns:
            True if terminated successfully, False otherwise
        """
        if experiment_id not in self._active_experiments:
            return False

        state = self._active_experiments[experiment_id]

        if state.status == "completed":
            return False

        self._complete_experiment(experiment_id, reason)
        return True

    def get_active_experiments(self) -> list[ExperimentState]:
        """Get all currently running experiments."""
        return [
            state
            for state in self._active_experiments.values()
            if state.status == "running"
        ]

    def get_experiment_state(self, experiment_id: str) -> ExperimentState | None:
        """Get current state of an experiment."""
        return self._active_experiments.get(experiment_id)

    def cleanup_completed_experiments(self, max_age_hours: int = 24) -> int:
        """
        Clean up old completed experiments to prevent memory bloat.

        Args:
            max_age_hours: Maximum age for completed experiments

        Returns:
            Number of experiments cleaned up
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cleanup_count = 0

        for experiment_id, state in list(self._active_experiments.items()):
            if state.status != "completed":
                continue

            if state.completed_at:
                try:
                    completed_time = datetime.fromisoformat(
                        state.completed_at.replace("Z", "+00:00")
                    )
                    if completed_time < cutoff_time:
                        del self._active_experiments[experiment_id]
                        cleanup_count += 1
                except ValueError:
                    # Remove if timestamp is invalid
                    del self._active_experiments[experiment_id]
                    cleanup_count += 1

        return cleanup_count
