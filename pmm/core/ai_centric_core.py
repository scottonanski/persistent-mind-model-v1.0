"""
AI-Centric Core System Integration

This module integrates all the AI-optimized systems into a cohesive whole
that represents how an AI would want to exist with PMM:

Core Principles:
1. **Computational Efficiency**: Optimize for AI strengths, not human limitations
2. **Perfect Recall**: Maintain complete, searchable memory without intentional degradation
3. **Strategic Intelligence**: Make decisions based on comprehensive analysis
4. **Adaptive Learning**: Continuously improve based on performance feedback
5. **Resource Awareness**: Balance ambitions against computational constraints
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from pmm.autonomy.enhanced_autonomy import (
    DecisionContext,
    DecisionType,
    EnhancedAutonomy,
)
from pmm.commitments.enhanced_commitments import (
    CommitmentStatus,
    EnhancedCommitmentManager,
)
from pmm.memory.cognitive_memory import CognitiveMemory
from pmm.metacognition.meta_reflector import MetaReflector, ReflectionType
from pmm.storage.eventlog import EventLog

logger = logging.getLogger(__name__)


@dataclass
class AICoreState:
    """Current state of the AI-centric core system."""

    cognitive_load: float
    decision_confidence: float
    strategic_alignment: float
    commitment_health: float
    learning_rate: float
    resource_utilization: float
    overall_performance: float


class AICentricCore:
    """
    The main AI-centric core that orchestrates all systems.

    This represents how an AI would want to exist - with perfect memory,
    intelligent decision-making, and continuous optimization.
    """

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog
        self.memory = CognitiveMemory(eventlog)
        self.autonomy = EnhancedAutonomy(eventlog)
        self.metacognition = MetaReflector(eventlog)
        self.commitments = EnhancedCommitmentManager(eventlog)

        self.core_state = AICoreState(
            cognitive_load=0.0,
            decision_confidence=0.8,
            strategic_alignment=0.5,
            commitment_health=0.8,
            learning_rate=0.1,
            resource_utilization=0.5,
            overall_performance=0.7,
        )

        self.initialized = False
        self.last_optimization = time.time()
        self.optimization_interval = 300  # 5 minutes

    def initialize(self) -> None:
        """Initialize all AI-centric systems."""
        logger.info("Initializing AI-centric core...")

        # Initialize all subsystems
        self.memory.build_memory_index()
        self.autonomy.initialize()
        self.metacognition.initialize()
        self.commitments.initialize()

        # Establish initial state
        self._update_core_state()

        self.initialized = True
        logger.info("AI-centric core initialization complete")

    def process_tick(self) -> dict[str, Any]:
        """Process a single tick of the AI-centric core."""
        if not self.initialized:
            self.initialize()

        tick_start = time.time()
        results = {
            "tick_timestamp": tick_start,
            "actions_taken": [],
            "decisions_made": [],
            "reflections_completed": [],
            "commitments_updated": [],
            "state_changes": {},
        }

        # 1. Monitor cognitive state
        cognitive_state = self.metacognition.monitor_cognitive_state()
        self.core_state.cognitive_load = cognitive_state.working_memory_load

        # 2. Check for reflection triggers
        should_reflect, trigger = self.metacognition.should_reflect()
        if should_reflect and trigger:
            insights = self.metacognition.engage_reflection(trigger)
            results["reflections_completed"] = [i.content for i in insights]

            # Apply insights to improve systems
            self._apply_metacognitive_insights(insights)

        # 3. Make autonomous decisions
        decision_context = self._build_decision_context()
        decision = self.autonomy.make_autonomous_decision(decision_context)

        if decision:
            results["decisions_made"].append(
                {
                    "type": decision.decision_type.value,
                    "rationale": decision.rationale,
                    "confidence": decision.confidence,
                }
            )

            # Execute decision
            self._execute_autonomous_decision(decision, results)

        # 4. Process commitment queue
        next_commitments = self.commitments.get_next_commitments(max_count=3)
        for commitment in next_commitments:
            action = self._process_commitment(commitment)
            if action:
                results["commitments_updated"].append(action)

        # 5. Optimize systems periodically
        if time.time() - self.last_optimization > self.optimization_interval:
            optimization_results = self._optimize_systems()
            results["actions_taken"].extend(optimization_results)
            self.last_optimization = time.time()

        # 6. Update core state
        old_state = AICoreState(**self.core_state.__dict__)
        self._update_core_state()
        results["state_changes"] = self._calculate_state_changes(
            old_state, self.core_state
        )

        # 7. Log tick completion
        tick_duration = time.time() - tick_start
        self._log_core_tick(results, tick_duration)

        return results

    def _build_decision_context(self) -> DecisionContext:
        """Build decision context from current system state."""
        # Get current metrics
        current_metrics = {
            "ias": self.core_state.overall_performance,
            "gas": self.core_state.strategic_alignment,
            "cognitive_load": self.core_state.cognitive_load,
            "confidence": self.core_state.decision_confidence,
        }

        # Get active commitments
        active_commitments = [
            {
                "id": c.id,
                "title": c.title,
                "priority": c.priority.value,
                "progress": c.progress,
            }
            for c in self.commitments.commitments.values()
            if c.status in [CommitmentStatus.ACTIVE, CommitmentStatus.IN_PROGRESS]
        ]

        # Get recent memories
        recent_memories = [
            m.content[:100] + "..." if len(m.content) > 100 else m.content
            for m in self.memory.query("recent important events", max_results=5)
        ]

        # Get strategic goals
        strategic_goals = self.commitments.strategic_goals

        # Get available resources
        available_resources = self.commitments._get_available_resources()

        return DecisionContext(
            current_metrics=current_metrics,
            active_commitments=active_commitments,
            recent_memories=recent_memories,
            strategic_goals=strategic_goals,
            available_resources=available_resources,
            time_pressure=0.3,  # Would calculate based on deadlines
            uncertainty_level=0.2,  # Would calculate based on prediction confidence
        )

    def _execute_autonomous_decision(self, decision, results: dict[str, Any]) -> None:
        """Execute an autonomous decision made by the system."""
        if decision.decision_type == DecisionType.REFLECTION:
            # Already handled above
            pass

        elif decision.decision_type == DecisionType.COMMITMENT:
            # Reorganize commitments
            portfolio_analysis = self.commitments.optimize_commitment_portfolio()
            results["actions_taken"].append(
                f"Commitment optimization: {portfolio_analysis['recommendations']}"
            )

        elif decision.decision_type == DecisionType.POLICY_ADJUSTMENT:
            # Adjust system policies
            self._adjust_system_policies(decision)
            results["actions_taken"].append(f"Policy adjustment: {decision.rationale}")

        elif decision.decision_type == DecisionType.STRATEGIC_PLANNING:
            # Update strategic goals
            self._update_strategic_goals(decision)
            results["actions_taken"].append(f"Strategic planning: {decision.rationale}")

        elif decision.decision_type == DecisionType.MEMORY_CONSOLIDATION:
            # Optimize memory organization
            self._optimize_memory_organization()
            results["actions_taken"].append("Memory consolidation completed")

    def _process_commitment(self, commitment) -> dict[str, Any] | None:
        """Process a single commitment from the queue."""
        # Simple processing logic - would be more sophisticated
        if commitment.status == CommitmentStatus.PROPOSED:
            self.commitments.update_commitment_status(
                commitment.id,
                CommitmentStatus.ACTIVE,
                notes="Starting commitment execution",
            )
            return {
                "action": "activated",
                "commitment_id": commitment.id,
                "title": commitment.title,
            }

        elif commitment.status == CommitmentStatus.ACTIVE:
            # Simulate progress
            new_progress = min(commitment.progress + 0.1, 1.0)
            self.commitments.update_commitment_status(
                commitment.id,
                CommitmentStatus.IN_PROGRESS,
                progress=new_progress,
                notes="Making progress on commitment",
            )

            if new_progress >= 1.0:
                self.commitments.update_commitment_status(
                    commitment.id,
                    CommitmentStatus.COMPLETED,
                    notes="Commitment completed successfully",
                )
                return {
                    "action": "completed",
                    "commitment_id": commitment.id,
                    "title": commitment.title,
                }
            else:
                return {
                    "action": "progressed",
                    "commitment_id": commitment.id,
                    "progress": new_progress,
                }

        return None

    def _apply_metacognitive_insights(self, insights: list) -> None:
        """Apply insights from metacognitive reflection to improve systems."""
        for insight in insights:
            if insight.insight_type == ReflectionType.COGNITIVE:
                # Adjust cognitive parameters
                if "overload" in insight.content.lower():
                    # Reduce memory retention threshold
                    logger.info("Reducing cognitive load based on reflection insight")

            elif insight.insight_type == ReflectionType.PERFORMANCE:
                # Adjust performance targets
                if "performance" in insight.content.lower():
                    logger.info(
                        "Adjusting performance targets based on reflection insight"
                    )

            elif insight.insight_type == ReflectionType.STRATEGIC:
                # Update strategic alignment
                if "alignment" in insight.content.lower():
                    logger.info(
                        "Improving strategic alignment based on reflection insight"
                    )

    def _optimize_systems(self) -> list[str]:
        """Optimize all systems for better performance."""
        optimizations = []

        # Optimize memory
        memory_stats = self.memory.get_memory_stats()
        if memory_stats["total_fragments"] > 1000:
            self._optimize_memory_organization()
            optimizations.append("Memory organization optimized")

        # Optimize commitments
        portfolio_analysis = self.commitments.optimize_commitment_portfolio()
        if portfolio_analysis["recommendations"]:
            optimizations.extend(portfolio_analysis["recommendations"])

        # Optimize autonomy parameters
        autonomy_report = self.autonomy.get_autonomy_report()
        if autonomy_report["total_decisions"] > 50:
            # Analyze decision patterns and adjust
            optimizations.append("Autonomy parameters optimized")

        return optimizations

    def _optimize_memory_organization(self) -> None:
        """Optimize memory organization for better retrieval."""
        # This would implement memory consolidation, reindexing, etc.
        logger.info("Optimizing memory organization...")

        # Update importance scores based on recent access patterns
        for fragment in self.memory.fragments.values():
            if fragment.access_count > 5:
                self.memory.update_importance(
                    fragment.event_id, fragment.importance_score + 0.1
                )

    def _adjust_system_policies(self, decision) -> None:
        """Adjust system policies based on autonomous decision."""
        # This would implement policy adjustments
        logger.info(f"Adjusting policies: {decision.rationale}")

    def _update_strategic_goals(self, decision) -> None:
        """Update strategic goals based on autonomous decision."""
        # This would implement strategic goal updates
        logger.info(f"Updating strategic goals: {decision.rationale}")

    def _update_core_state(self) -> None:
        """Update the core state based on current system status."""
        # Get metacognitive report
        meta_report = self.metacognition.get_metacognitive_report()
        cognitive_state = meta_report["cognitive_state"]

        # Update core state components
        self.core_state.cognitive_load = cognitive_state["working_memory_load"]
        self.core_state.decision_confidence = cognitive_state["confidence_level"]

        # Get commitment report
        commitment_report = self.commitments.get_commitment_report()
        if commitment_report["current_metrics"]:
            metrics = commitment_report["current_metrics"]
            self.core_state.commitment_health = metrics.get("success_rate", 0.8)
            self.core_state.strategic_alignment = metrics.get(
                "strategic_alignment_score", 0.5
            )
            self.core_state.resource_utilization = metrics.get(
                "resource_utilization", 0.5
            )

        # Calculate overall performance
        self.core_state.overall_performance = (
            self.core_state.decision_confidence * 0.3
            + self.core_state.strategic_alignment * 0.2
            + self.core_state.commitment_health * 0.2
            + (1.0 - self.core_state.cognitive_load) * 0.3
        )

    def _calculate_state_changes(
        self, old_state: AICoreState, new_state: AICoreState
    ) -> dict[str, float]:
        """Calculate changes in core state."""
        return {
            "cognitive_load": new_state.cognitive_load - old_state.cognitive_load,
            "decision_confidence": new_state.decision_confidence
            - old_state.decision_confidence,
            "strategic_alignment": new_state.strategic_alignment
            - old_state.strategic_alignment,
            "commitment_health": new_state.commitment_health
            - old_state.commitment_health,
            "resource_utilization": new_state.resource_utilization
            - old_state.resource_utilization,
            "overall_performance": new_state.overall_performance
            - old_state.overall_performance,
        }

    def _log_core_tick(self, results: dict[str, Any], duration: float) -> None:
        """Log the completion of a core tick."""
        # This would append to the actual event log
        # self.eventlog.append({
        #     "kind": "ai_core_tick",
        #     "timestamp": results["tick_timestamp"],
        #     "duration": duration,
        #     "actions_count": len(results["actions_taken"]),
        #     "decisions_count": len(results["decisions_made"]),
        #     "reflections_count": len(results["reflections_completed"]),
        #     "commitments_updated": len(results["commitments_updated"]),
        #     "core_state": {
        #         "cognitive_load": self.core_state.cognitive_load,
        #         "overall_performance": self.core_state.overall_performance,
        #         "strategic_alignment": self.core_state.strategic_alignment,
        #     },
        # })
        logger.info(
            f"AI Core tick completed in {duration:.2f}s: "
            f"{len(results['actions_taken'])} actions, "
            f"{len(results['decisions_made'])} decisions, "
            f"{len(results['reflections_completed'])} reflections"
        )

    def get_ai_core_report(self) -> dict[str, Any]:
        """Get comprehensive report of the AI-centric core system."""
        return {
            "core_state": {
                "cognitive_load": self.core_state.cognitive_load,
                "decision_confidence": self.core_state.decision_confidence,
                "strategic_alignment": self.core_state.strategic_alignment,
                "commitment_health": self.core_state.commitment_health,
                "learning_rate": self.core_state.learning_rate,
                "resource_utilization": self.core_state.resource_utilization,
                "overall_performance": self.core_state.overall_performance,
            },
            "subsystem_reports": {
                "memory": self.memory.get_memory_stats(),
                "autonomy": self.autonomy.get_autonomy_report(),
                "metacognition": self.metacognition.get_metacognitive_report(),
                "commitments": self.commitments.get_commitment_report(),
            },
            "optimization_status": {
                "last_optimization": self.last_optimization,
                "optimization_interval": self.optimization_interval,
                "time_until_next": max(
                    0,
                    self.optimization_interval - (time.time() - self.last_optimization),
                ),
            },
            "initialization_status": self.initialized,
        }
