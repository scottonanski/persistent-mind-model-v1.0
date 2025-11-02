"""
AI-Optimized Commitment Management System

This commitment system is designed specifically for AI capabilities:
1. **Scalable Commitment Tracking**: Handle thousands of commitments without cognitive overload
2. **Intelligent Prioritization**: Dynamic priority adjustment based on strategic value and context
3. **Adaptive Execution**: Modify execution strategies based on real-time feedback
4. **Commitment Networks**: Understand relationships and dependencies between commitments
5. **Resource-Aware Planning**: Balance commitments against available computational resources
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pmm.memory.cognitive_memory import CognitiveMemory
from pmm.storage.eventlog import EventLog

logger = logging.getLogger(__name__)


class CommitmentStatus(Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELEGATED = "delegated"


class CommitmentPriority(Enum):
    CRITICAL = 1  # System-critical, must complete
    HIGH = 2  # Important for strategic goals
    MEDIUM = 3  # Normal operational commitments
    LOW = 4  # Nice to have, can be deferred
    BACKGROUND = 5  # Continuous processes, no deadline


@dataclass
class Commitment:
    """Enhanced commitment representation for AI-centric management."""

    id: int
    title: str
    description: str
    status: CommitmentStatus
    priority: CommitmentPriority
    created_at: float
    updated_at: float
    deadline: float | None = None
    estimated_effort: float = 1.0  # Estimated computational cost
    actual_effort: float = 0.0
    progress: float = 0.0  # 0-1 completion
    dependencies: list[int] = field(
        default_factory=list
    )  # IDs of dependent commitments
    dependents: list[int] = field(
        default_factory=list
    )  # IDs of commitments that depend on this
    tags: list[str] = field(default_factory=list)
    strategic_value: float = 0.5  # 0-1 alignment with strategic goals
    execution_history: list[dict] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    resource_requirements: dict[str, float] = field(default_factory=dict)
    auto_retry: bool = False
    max_retries: int = 3
    retry_count: int = 0


@dataclass
class CommitmentPlan:
    """Execution plan for a commitment."""

    commitment_id: int
    steps: list[str]
    estimated_duration: float
    resource_allocation: dict[str, float]
    risk_factors: list[str]
    mitigation_strategies: list[str]
    checkpoints: list[float]  # Progress points for review


@dataclass
class CommitmentMetrics:
    """Metrics for commitment system performance."""

    total_commitments: int
    active_commitments: int
    completion_rate: float
    average_completion_time: float
    overdue_count: int
    success_rate: float
    strategic_alignment_score: float
    resource_utilization: float


class EnhancedCommitmentManager:
    """
    AI-optimized commitment management system.

    Unlike human-based systems, this leverages AI strengths:
    - Perfect recall of all commitments
    - Computational resource awareness
    - Dynamic priority optimization
    - Pattern recognition for execution strategies
    """

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog
        self.memory = CognitiveMemory(eventlog)
        self.commitments: dict[int, Commitment] = {}
        self.commitment_network: dict[int, set[int]] = {}  # Dependency graph
        self.execution_queue: list[int] = []
        self.resource_pool: dict[str, float] = {
            "compute": 1.0,
            "memory": 1.0,
            "time": 1.0,
            "attention": 1.0,
        }
        self.strategic_goals: list[str] = []
        self.performance_history: list[CommitmentMetrics] = []

    def initialize(self) -> None:
        """Initialize the commitment management system."""
        logger.info("Initializing enhanced commitment system...")
        self.memory.build_memory_index()
        self._load_existing_commitments()
        self._build_dependency_network()
        self._update_execution_queue()
        self._extract_strategic_goals()

    def create_commitment(
        self,
        title: str,
        description: str,
        priority: CommitmentPriority = CommitmentPriority.MEDIUM,
        deadline: float | None = None,
        dependencies: list[int] = None,
        tags: list[str] = None,
        strategic_value: float = 0.5,
    ) -> int:
        """Create a new commitment with AI-optimized validation."""

        # Generate commitment ID
        new_id = max(self.commitments.keys(), default=0) + 1

        # Validate dependencies
        if dependencies:
            for dep_id in dependencies:
                if dep_id not in self.commitments:
                    raise ValueError(f"Dependency {dep_id} does not exist")

        # Estimate effort based on description and historical patterns
        estimated_effort = self._estimate_effort(description, tags or [])

        # Check resource availability
        if not self._check_resource_availability(estimated_effort):
            logger.warning("Limited resources available for new commitment")

        commitment = Commitment(
            id=new_id,
            title=title,
            description=description,
            status=CommitmentStatus.PROPOSED,
            priority=priority,
            created_at=time.time(),
            updated_at=time.time(),
            deadline=deadline,
            estimated_effort=estimated_effort,
            dependencies=dependencies or [],
            tags=tags or [],
            strategic_value=strategic_value,
        )

        self.commitments[new_id] = commitment

        # Update dependency network
        if dependencies:
            for dep_id in dependencies:
                if dep_id not in self.commitment_network:
                    self.commitment_network[dep_id] = set()
                self.commitment_network[dep_id].add(new_id)

        # Create execution plan
        plan = self._create_execution_plan(commitment)
        commitment.execution_history.append(
            {"action": "created", "timestamp": time.time(), "plan": plan}
        )

        # Log to eventlog
        self._log_commitment_event("commitment_created", commitment)

        # Update queue
        self._update_execution_queue()

        logger.info(f"Created commitment {new_id}: {title}")
        return new_id

    def update_commitment_status(
        self,
        commitment_id: int,
        new_status: CommitmentStatus,
        progress: float | None = None,
        notes: str | None = None,
    ) -> bool:
        """Update commitment status with intelligent dependency handling."""

        if commitment_id not in self.commitments:
            return False

        commitment = self.commitments[commitment_id]
        old_status = commitment.status

        # Validate status transitions
        if not self._validate_status_transition(old_status, new_status):
            logger.warning(f"Invalid status transition: {old_status} -> {new_status}")
            return False

        # Update commitment
        commitment.status = new_status
        commitment.updated_at = time.time()

        if progress is not None:
            commitment.progress = max(0, min(progress, 1.0))

        # Handle dependency cascades
        if new_status == CommitmentStatus.COMPLETED:
            self._handle_completion_cascade(commitment_id)
        elif new_status == CommitmentStatus.FAILED:
            self._handle_failure_cascade(commitment_id)

        # Record in execution history
        commitment.execution_history.append(
            {
                "action": "status_changed",
                "old_status": old_status.value,
                "new_status": new_status.value,
                "timestamp": time.time(),
                "progress": commitment.progress,
                "notes": notes,
            }
        )

        # Log to eventlog
        self._log_commitment_event("commitment_updated", commitment)

        # Update queue and metrics
        self._update_execution_queue()
        self._update_metrics()

        logger.info(
            f"Updated commitment {commitment_id}: {old_status.value} -> {new_status.value}"
        )
        return True

    def get_next_commitments(self, max_count: int = 5) -> list[Commitment]:
        """Get next commitments to work on based on intelligent prioritization."""
        if not self.execution_queue:
            self._update_execution_queue()

        available_commitments = []
        resources_available = self._get_available_resources()

        for commitment_id in self.execution_queue[
            : max_count * 2
        ]:  # Check more than needed
            commitment = self.commitments[commitment_id]

            # Check if commitment can be executed
            if self._can_execute_commitment(commitment, resources_available):
                available_commitments.append(commitment)

                if len(available_commitments) >= max_count:
                    break

        return available_commitments

    def optimize_commitment_portfolio(self) -> dict[str, Any]:
        """Optimize the overall commitment portfolio for maximum strategic value."""
        analysis = {
            "total_commitments": len(self.commitments),
            "active_commitments": len(
                [
                    c
                    for c in self.commitments.values()
                    if c.status
                    in [CommitmentStatus.ACTIVE, CommitmentStatus.IN_PROGRESS]
                ]
            ),
            "overdue_commitments": len(
                [
                    c
                    for c in self.commitments.values()
                    if c.deadline
                    and time.time() > c.deadline
                    and c.status
                    not in [CommitmentStatus.COMPLETED, CommitmentStatus.CANCELLED]
                ]
            ),
            "strategic_alignment": self._calculate_strategic_alignment(),
            "resource_pressure": self._calculate_resource_pressure(),
            "recommendations": [],
        }

        # Generate optimization recommendations
        if analysis["overdue_commitments"] > 0:
            analysis["recommendations"].append(
                f"Reprioritize or renegotiate {analysis['overdue_commitments']} overdue commitments"
            )

        if analysis["resource_pressure"] > 0.8:
            analysis["recommendations"].append(
                "Resource pressure high - consider deferring low-priority commitments"
            )

        if analysis["strategic_alignment"] < 0.5:
            analysis["recommendations"].append(
                "Low strategic alignment - review commitment portfolio against goals"
            )

        return analysis

    def _load_existing_commitments(self) -> None:
        """Load existing commitments from event log."""
        commitment_events = self.memory.query("commitment", max_results=1000)

        for event in commitment_events:
            # This would parse actual commitment events from the log
            # Simplified for demonstration
            pass

    def _build_dependency_network(self) -> None:
        """Build the dependency network from existing commitments."""
        self.commitment_network = {}

        for commitment in self.commitments.values():
            for dep_id in commitment.dependencies:
                if dep_id not in self.commitment_network:
                    self.commitment_network[dep_id] = set()
                self.commitment_network[dep_id].add(commitment.id)

    def _update_execution_queue(self) -> None:
        """Update the execution queue based on priorities and dependencies."""
        # Filter executable commitments
        executable = []

        for commitment in self.commitments.values():
            if commitment.status in [
                CommitmentStatus.ACTIVE,
                CommitmentStatus.PROPOSED,
            ] and self._dependencies_satisfied(commitment):
                executable.append(commitment)

        # Sort by priority (lower number = higher priority), then by strategic value
        executable.sort(
            key=lambda c: (c.priority.value, -c.strategic_value, c.created_at)
        )

        self.execution_queue = [c.id for c in executable]

    def _extract_strategic_goals(self) -> None:
        """Extract strategic goals from memory."""
        goal_memories = self.memory.query(
            "strategic goal objective mission", max_results=10
        )
        self.strategic_goals = [m.content for m in goal_memories]

    def _estimate_effort(self, description: str, tags: list[str]) -> float:
        """Estimate computational effort based on description and historical patterns."""
        base_effort = 1.0

        # Analyze description complexity
        if len(description) > 500:
            base_effort += 0.5
        elif len(description) > 200:
            base_effort += 0.2

        # Analyze tags for effort indicators
        high_effort_tags = ["complex", "research", "analysis", "development"]
        for tag in tags:
            if tag.lower() in high_effort_tags:
                base_effort += 0.3

        # Look at historical similar commitments
        similar_memories = self.memory.query(description, max_results=5)
        if similar_memories:
            # Would extract actual effort from similar historical commitments
            base_effort *= 1.1  # Slight increase for complexity based on history

        return base_effort

    def _check_resource_availability(self, required_effort: float) -> bool:
        """Check if sufficient resources are available."""
        available = sum(self.resource_pool.values()) / len(self.resource_pool)
        return available >= required_effort * 0.3  # Require 30% of total resources

    def _create_execution_plan(self, commitment: Commitment) -> CommitmentPlan:
        """Create an execution plan for the commitment."""
        # Simplified plan creation
        steps = [
            "Analyze requirements and constraints",
            "Identify necessary resources and dependencies",
            "Execute main task",
            "Review and validate results",
            "Finalize and document outcomes",
        ]

        return CommitmentPlan(
            commitment_id=commitment.id,
            steps=steps,
            estimated_duration=commitment.estimated_effort * 3600,  # Convert to seconds
            resource_allocation={"compute": commitment.estimated_effort * 0.5},
            risk_factors=["resource_constraints", "dependency_delays"],
            mitigation_strategies=["monitor_resources", "track_dependencies"],
            checkpoints=[0.25, 0.5, 0.75, 1.0],
        )

    def _validate_status_transition(
        self, old_status: CommitmentStatus, new_status: CommitmentStatus
    ) -> bool:
        """Validate that a status transition is allowed."""
        # Define valid transitions
        valid_transitions = {
            CommitmentStatus.PROPOSED: [
                CommitmentStatus.ACTIVE,
                CommitmentStatus.CANCELLED,
            ],
            CommitmentStatus.ACTIVE: [
                CommitmentStatus.IN_PROGRESS,
                CommitmentStatus.CANCELLED,
            ],
            CommitmentStatus.IN_PROGRESS: [
                CommitmentStatus.COMPLETED,
                CommitmentStatus.FAILED,
                CommitmentStatus.BLOCKED,
            ],
            CommitmentStatus.BLOCKED: [
                CommitmentStatus.IN_PROGRESS,
                CommitmentStatus.CANCELLED,
            ],
            CommitmentStatus.COMPLETED: [],  # Terminal state
            CommitmentStatus.FAILED: [CommitmentStatus.ACTIVE],  # Can retry
            CommitmentStatus.CANCELLED: [],  # Terminal state
            CommitmentStatus.DELEGATED: [
                CommitmentStatus.COMPLETED,
                CommitmentStatus.FAILED,
            ],
        }

        return new_status in valid_transitions.get(old_status, [])

    def _handle_completion_cascade(self, commitment_id: int) -> None:
        """Handle cascading effects when a commitment is completed."""
        # Update dependent commitments
        if commitment_id in self.commitment_network:
            for dependent_id in self.commitment_network[commitment_id]:
                dependent = self.commitments[dependent_id]
                if dependent.status == CommitmentStatus.BLOCKED:
                    # Check if all dependencies are now satisfied
                    if self._dependencies_satisfied(dependent):
                        self.update_commitment_status(
                            dependent_id,
                            CommitmentStatus.ACTIVE,
                            notes="Dependencies satisfied",
                        )

    def _handle_failure_cascade(self, commitment_id: int) -> None:
        """Handle cascading effects when a commitment fails."""
        # Block dependent commitments
        if commitment_id in self.commitment_network:
            for dependent_id in self.commitment_network[commitment_id]:
                dependent = self.commitments[dependent_id]
                if dependent.status in [
                    CommitmentStatus.ACTIVE,
                    CommitmentStatus.IN_PROGRESS,
                ]:
                    self.update_commitment_status(
                        dependent_id,
                        CommitmentStatus.BLOCKED,
                        notes=f"Dependency {commitment_id} failed",
                    )

    def _dependencies_satisfied(self, commitment: Commitment) -> bool:
        """Check if all dependencies for a commitment are satisfied."""
        for dep_id in commitment.dependencies:
            if dep_id not in self.commitments:
                return False
            dep_commitment = self.commitments[dep_id]
            if dep_commitment.status != CommitmentStatus.COMPLETED:
                return False
        return True

    def _can_execute_commitment(
        self, commitment: Commitment, available_resources: dict[str, float]
    ) -> bool:
        """Check if a commitment can be executed with available resources."""
        # Check resource requirements
        for resource, required in commitment.resource_requirements.items():
            if available_resources.get(resource, 0) < required:
                return False

        # Check if not blocked
        if commitment.status == CommitmentStatus.BLOCKED:
            return False

        return True

    def _get_available_resources(self) -> dict[str, float]:
        """Get currently available resources."""
        # Calculate resource usage by active commitments
        active_usage = {"compute": 0.0, "memory": 0.0, "time": 0.0, "attention": 0.0}

        for commitment in self.commitments.values():
            if commitment.status == CommitmentStatus.IN_PROGRESS:
                for resource, usage in commitment.resource_requirements.items():
                    active_usage[resource] += usage

        # Calculate available resources
        available = {}
        for resource, total in self.resource_pool.items():
            available[resource] = total - active_usage.get(resource, 0)

        return available

    def _calculate_strategic_alignment(self) -> float:
        """Calculate how well commitments align with strategic goals."""
        if not self.strategic_goals or not self.commitments:
            return 0.0

        total_value = sum(c.strategic_value for c in self.commitments.values())
        return total_value / len(self.commitments)

    def _calculate_resource_pressure(self) -> float:
        """Calculate current resource pressure (0-1 scale)."""
        total_usage = 0.0
        total_capacity = 0.0

        for resource, capacity in self.resource_pool.items():
            total_capacity += capacity
            # Calculate usage from active commitments
            usage = sum(
                c.resource_requirements.get(resource, 0)
                for c in self.commitments.values()
                if c.status == CommitmentStatus.IN_PROGRESS
            )
            total_usage += usage

        return total_usage / total_capacity if total_capacity > 0 else 0.0

    def _update_metrics(self) -> None:
        """Update performance metrics."""
        metrics = CommitmentMetrics(
            total_commitments=len(self.commitments),
            active_commitments=len(
                [
                    c
                    for c in self.commitments.values()
                    if c.status
                    in [CommitmentStatus.ACTIVE, CommitmentStatus.IN_PROGRESS]
                ]
            ),
            completion_rate=self._calculate_completion_rate(),
            average_completion_time=self._calculate_avg_completion_time(),
            overdue_count=len(
                [
                    c
                    for c in self.commitments.values()
                    if c.deadline
                    and time.time() > c.deadline
                    and c.status
                    not in [CommitmentStatus.COMPLETED, CommitmentStatus.CANCELLED]
                ]
            ),
            success_rate=self._calculate_success_rate(),
            strategic_alignment_score=self._calculate_strategic_alignment(),
            resource_utilization=self._calculate_resource_pressure(),
        )

        self.performance_history.append(metrics)

        # Keep only recent history
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-50:]

    def _calculate_completion_rate(self) -> float:
        """Calculate commitment completion rate."""
        if not self.commitments:
            return 0.0

        completed = len(
            [
                c
                for c in self.commitments.values()
                if c.status == CommitmentStatus.COMPLETED
            ]
        )
        return completed / len(self.commitments)

    def _calculate_avg_completion_time(self) -> float:
        """Calculate average time to complete commitments."""
        completed_commitments = [
            c
            for c in self.commitments.values()
            if c.status == CommitmentStatus.COMPLETED
        ]

        if not completed_commitments:
            return 0.0

        total_time = sum(c.updated_at - c.created_at for c in completed_commitments)
        return total_time / len(completed_commitments)

    def _calculate_success_rate(self) -> float:
        """Calculate success rate (completed vs failed)."""
        finished = [
            c
            for c in self.commitments.values()
            if c.status in [CommitmentStatus.COMPLETED, CommitmentStatus.FAILED]
        ]

        if not finished:
            return 1.0  # No failures yet

        successful = len(
            [c for c in finished if c.status == CommitmentStatus.COMPLETED]
        )
        return successful / len(finished)

    def _log_commitment_event(self, event_type: str, commitment: Commitment) -> None:
        """Log commitment events to the event log."""
        # This would append to the actual event log
        # self.eventlog.append({
        #     "kind": "commitment_event",
        #     "event_type": event_type,
        #     "commitment_id": commitment.id,
        #     "title": commitment.title,
        #     "status": commitment.status.value,
        #     "priority": commitment.priority.value,
        #     "progress": commitment.progress,
        #     "strategic_value": commitment.strategic_value,
        # })
        logger.debug(f"Commitment event: {event_type} for commitment {commitment.id}")

    def get_commitment_report(self) -> dict[str, Any]:
        """Get comprehensive commitment system report."""
        current_metrics = (
            self.performance_history[-1] if self.performance_history else None
        )

        return {
            "total_commitments": len(self.commitments),
            "active_commitments": len(
                [
                    c
                    for c in self.commitments.values()
                    if c.status
                    in [CommitmentStatus.ACTIVE, CommitmentStatus.IN_PROGRESS]
                ]
            ),
            "execution_queue_length": len(self.execution_queue),
            "strategic_goals": self.strategic_goals,
            "current_metrics": current_metrics.__dict__ if current_metrics else None,
            "resource_pool": self.resource_pool,
            "upcoming_commitments": [
                {
                    "id": self.commitments[cid].id,
                    "title": self.commitments[cid].title,
                    "priority": self.commitments[cid].priority.value,
                    "strategic_value": self.commitments[cid].strategic_value,
                }
                for cid in self.execution_queue[:5]
            ],
        }
