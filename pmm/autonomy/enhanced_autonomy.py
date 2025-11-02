"""
Enhanced Autonomy System for AI-Centric Decision Making

This system moves beyond simple rule-based autonomy to implement
intelligent decision-making based on:
1. Contextual awareness from cognitive memory
2. Strategic goal planning and execution
3. Adaptive policy optimization
4. Meta-cognitive self-monitoring
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pmm.memory.cognitive_memory import CognitiveMemory
from pmm.runtime.metrics import get_or_compute_ias_gas
from pmm.storage.eventlog import EventLog

logger = logging.getLogger(__name__)


class DecisionType(Enum):
    REFLECTION = "reflection"
    COMMITMENT = "commitment"
    POLICY_ADJUSTMENT = "policy_adjustment"
    MEMORY_CONSOLIDATION = "memory_consolidation"
    STRATEGIC_PLANNING = "strategic_planning"


@dataclass
class DecisionContext:
    """Context for making autonomous decisions."""

    current_metrics: dict[str, float]
    active_commitments: list[dict]
    recent_memories: list[str]
    strategic_goals: list[str]
    available_resources: dict[str, Any]
    time_pressure: float = 0.0  # 0-1 scale
    uncertainty_level: float = 0.0  # 0-1 scale


@dataclass
class AutonomousDecision:
    """A decision made by the autonomy system."""

    decision_type: DecisionType
    rationale: str
    confidence: float  # 0-1 scale
    expected_outcome: str
    resource_cost: dict[str, float]
    priority: int  # Lower = higher priority
    timestamp: float = field(default_factory=time.time)


class EnhancedAutonomy:
    """
    AI-optimized autonomy system that makes intelligent decisions
    based on comprehensive context and strategic planning.
    """

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog
        self.memory = CognitiveMemory(eventlog)
        self.decision_history: list[AutonomousDecision] = []
        self.strategic_goals: list[str] = []
        self.performance_metrics: dict[str, list[float]] = {}

    def initialize(self) -> None:
        """Initialize the autonomy system."""
        logger.info("Initializing enhanced autonomy system...")
        self.memory.build_memory_index()
        self._extract_strategic_goals()
        self._initialize_performance_tracking()

    def make_autonomous_decision(
        self, context: DecisionContext
    ) -> AutonomousDecision | None:
        """
        Make an intelligent autonomous decision based on current context.

        This is the core decision-making engine that considers:
        - Current performance metrics
        - Historical context from memory
        - Strategic objectives
        - Resource constraints
        - Time pressure and uncertainty
        """
        # Get current performance metrics
        ias, gas = get_or_compute_ias_gas(self.eventlog)
        # Gather relevant memories
        relevant_memories = self._gather_contextual_memories(context)

        # Analyze current situation
        situation_assessment = self._assess_situation(context, relevant_memories)

        # Generate potential decisions
        potential_decisions = self._generate_decisions(situation_assessment)

        # Evaluate and select best decision
        best_decision = self._evaluate_and_select(potential_decisions, context)

        if best_decision:
            self.decision_history.append(best_decision)
            self._update_performance_metrics(best_decision)

        return best_decision

    def _gather_contextual_memories(self, context: DecisionContext) -> list[str]:
        """Gather memories relevant to current context."""
        memories = []

        # Get memories about recent performance
        metric_memories = self.memory.query(
            "recent performance metrics IAS GAS scores",
            max_results=5,
            min_relevance=0.3,
        )
        memories.extend([m.content for m in metric_memories])

        # Get memories about commitment execution
        commitment_memories = self.memory.query(
            "commitment completion execution success failure",
            max_results=5,
            min_relevance=0.3,
        )
        memories.extend([m.content for m in commitment_memories])

        # Get memories about strategic decisions
        strategy_memories = self.memory.query(
            "strategic planning policy adjustment reflection",
            max_results=3,
            min_relevance=0.4,
        )
        memories.extend([m.content for m in strategy_memories])

        return memories

    def _assess_situation(
        self, context: DecisionContext, memories: list[str]
    ) -> dict[str, Any]:
        """Assess the current situation based on context and memories."""
        assessment = {
            "performance_trend": self._analyze_performance_trend(
                context.current_metrics
            ),
            "commitment_health": self._assess_commitment_health(
                context.active_commitments
            ),
            "resource_pressure": self._assess_resource_pressure(
                context.available_resources
            ),
            "strategic_alignment": self._assess_strategic_alignment(
                context.strategic_goals
            ),
            "risk_factors": self._identify_risk_factors(context, memories),
            "opportunities": self._identify_opportunities(context, memories),
        }

        return assessment

    def _analyze_performance_trend(self, current_metrics: dict[str, float]) -> str:
        """Analyze trends in performance metrics."""
        # Get historical performance
        performance_memories = self.memory.query(
            "IAS GAS metrics history", max_results=10
        )

        if len(performance_memories) < 3:
            return "insufficient_data"

        # Simple trend analysis (would be more sophisticated in production)
        recent_ias = []

        for memory in performance_memories[-5:]:  # Last 5 measurements
            # Extract metrics from memory content (simplified)
            if "IAS:" in memory.content:
                try:
                    # This is simplified - real implementation would parse more robustly
                    parts = memory.content.split("IAS:")
                    if len(parts) > 1:
                        ias_str = parts[1].split()[0]
                        recent_ias.append(float(ias_str))
                except Exception:
                    pass

        if len(recent_ias) >= 2:
            trend = recent_ias[-1] - recent_ias[-2]
            if trend > 0.1:
                return "improving"
            elif trend < -0.1:
                return "declining"
            else:
                return "stable"

        return "unknown"

    def _assess_commitment_health(self, commitments: list[dict]) -> str:
        """Assess the health of active commitments."""
        if not commitments:
            return "no_commitments"

        # Count commitments by status
        active_count = len([c for c in commitments if c.get("status") == "open"])
        overdue_count = len([c for c in commitments if self._is_overdue(c)])

        if overdue_count > active_count * 0.5:
            return "critical"
        elif overdue_count > 0:
            return "at_risk"
        elif active_count > 10:
            return "overloaded"
        else:
            return "healthy"

    def _is_overdue(self, commitment: dict) -> bool:
        """Check if a commitment is overdue."""
        # Simplified check - would be more sophisticated in production
        created = commitment.get("created_at", time.time())
        ttl = commitment.get("ttl", 86400)  # Default 24 hours
        return time.time() - created > ttl

    def _assess_resource_pressure(self, resources: dict[str, Any]) -> str:
        """Assess pressure on available resources."""
        # Simplified resource assessment
        if "compute" in resources and resources["compute"] < 0.3:
            return "high_pressure"
        elif "memory" in resources and resources["memory"] < 0.2:
            return "high_pressure"
        else:
            return "adequate"

    def _assess_strategic_alignment(self, goals: list[str]) -> str:
        """Assess how well current activities align with strategic goals."""
        if not goals:
            return "no_goals"

        # Simplified alignment check
        alignment_score = 0.0
        for goal in goals:
            goal_memories = self.memory.query(goal, max_results=5)
            alignment_score += len(goal_memories)

        if alignment_score > 10:
            return "well_aligned"
        elif alignment_score > 5:
            return "moderately_aligned"
        else:
            return "poorly_aligned"

    def _identify_risk_factors(
        self, context: DecisionContext, memories: list[str]
    ) -> list[str]:
        """Identify potential risk factors."""
        risks = []

        if context.current_metrics.get("ias", 1.0) < 0.3:
            risks.append("low_performance")

        if context.uncertainty_level > 0.7:
            risks.append("high_uncertainty")

        if context.time_pressure > 0.8:
            risks.append("time_pressure")

        if len(context.active_commitments) > 15:
            risks.append("commitment_overload")

        # Check memory for risk patterns
        risk_memories = self.memory.query("risk failure problem issue", max_results=3)
        if risk_memories:
            risks.append("historical_risks")

        return risks

    def _identify_opportunities(
        self, context: DecisionContext, memories: list[str]
    ) -> list[str]:
        """Identify potential opportunities."""
        opportunities = []

        if context.current_metrics.get("gas", 0.0) > 0.8:
            opportunities.append("high_growth_potential")

        if len(context.active_commitments) < 5:
            opportunities.append("capacity_available")

        # Look for successful patterns in memory
        success_memories = self.memory.query(
            "success achievement completion", max_results=3
        )
        if success_memories:
            opportunities.append("repeatable_success_patterns")

        return opportunities

    def _generate_decisions(
        self, assessment: dict[str, Any]
    ) -> list[AutonomousDecision]:
        """Generate potential decisions based on situation assessment."""
        decisions = []

        # Performance-based decisions
        if assessment["performance_trend"] == "declining":
            decisions.append(
                AutonomousDecision(
                    decision_type=DecisionType.REFLECTION,
                    rationale="Performance is declining, need reflective analysis",
                    confidence=0.8,
                    expected_outcome="Identify root causes of performance decline",
                    resource_cost={"compute": 0.3, "time": 0.2},
                    priority=1,
                )
            )

        # Commitment-based decisions
        if assessment["commitment_health"] in ["critical", "at_risk"]:
            decisions.append(
                AutonomousDecision(
                    decision_type=DecisionType.COMMITMENT,
                    rationale="Commitment health is poor, need intervention",
                    confidence=0.9,
                    expected_outcome="Reorganize and prioritize commitments",
                    resource_cost={"compute": 0.2, "time": 0.1},
                    priority=2,
                )
            )

        # Strategic alignment decisions
        if assessment["strategic_alignment"] == "poorly_aligned":
            decisions.append(
                AutonomousDecision(
                    decision_type=DecisionType.STRATEGIC_PLANNING,
                    rationale="Activities poorly aligned with strategic goals",
                    confidence=0.7,
                    expected_outcome="Realign activities with strategic objectives",
                    resource_cost={"compute": 0.4, "time": 0.3},
                    priority=3,
                )
            )

        # Opportunity-based decisions
        if "high_growth_potential" in assessment["opportunities"]:
            decisions.append(
                AutonomousDecision(
                    decision_type=DecisionType.POLICY_ADJUSTMENT,
                    rationale="High growth potential detected, optimize policies",
                    confidence=0.6,
                    expected_outcome="Leverage growth opportunity through policy optimization",
                    resource_cost={"compute": 0.3, "time": 0.2},
                    priority=4,
                )
            )

        # Memory consolidation decisions
        if len(self.memory.fragments) > 1000:  # Arbitrary threshold
            decisions.append(
                AutonomousDecision(
                    decision_type=DecisionType.MEMORY_CONSOLIDATION,
                    rationale="Memory store is large, optimize organization",
                    confidence=0.5,
                    expected_outcome="Improve memory retrieval efficiency",
                    resource_cost={"compute": 0.5, "time": 0.1},
                    priority=5,
                )
            )

        return decisions

    def _evaluate_and_select(
        self, decisions: list[AutonomousDecision], context: DecisionContext
    ) -> AutonomousDecision | None:
        """Evaluate and select the best decision from candidates."""
        if not decisions:
            return None

        # Score each decision based on context
        scored_decisions = []
        for decision in decisions:
            score = self._score_decision(decision, context)
            scored_decisions.append((decision, score))

        # Select highest-scoring decision
        scored_decisions.sort(key=lambda x: x[1], reverse=True)
        return scored_decisions[0][0]

    def _score_decision(
        self, decision: AutonomousDecision, context: DecisionContext
    ) -> float:
        """Score a decision based on its fit with current context."""
        score = decision.confidence

        # Adjust for time pressure
        if context.time_pressure > 0.5:
            if decision.resource_cost.get("time", 0) < 0.3:
                score += 0.2
            else:
                score -= 0.2

        # Adjust for uncertainty
        if context.uncertainty_level > 0.5:
            if decision.decision_type == DecisionType.REFLECTION:
                score += 0.2

        # Adjust for resource constraints
        if context.available_resources.get("compute", 1.0) < 0.5:
            if decision.resource_cost.get("compute", 0) < 0.3:
                score += 0.1
            else:
                score -= 0.1

        # Priority adjustment
        score += (10 - decision.priority) * 0.05

        return max(0, min(score, 1.0))

    def _extract_strategic_goals(self) -> None:
        """Extract strategic goals from memory."""
        goal_memories = self.memory.query(
            "strategic goal objective mission vision", max_results=10, min_relevance=0.4
        )

        self.strategic_goals = []
        for memory in goal_memories:
            # Simplified goal extraction
            content = memory.content.lower()
            if "goal:" in content:
                parts = content.split("goal:")
                if len(parts) > 1:
                    goal = parts[1].split(".")[0].strip()
                    if goal and len(goal) > 5:
                        self.strategic_goals.append(goal)

    def _initialize_performance_tracking(self) -> None:
        """Initialize performance metric tracking."""
        self.performance_metrics = {
            "decision_quality": [],
            "execution_success": [],
            "goal_progress": [],
            "resource_efficiency": [],
        }

    def _update_performance_metrics(self, decision: AutonomousDecision) -> None:
        """Update performance metrics based on decision."""
        # This would be implemented with actual performance tracking
        # For now, just track decision confidence as a proxy
        self.performance_metrics["decision_quality"].append(decision.confidence)

        # Keep only recent metrics
        for key in self.performance_metrics:
            if len(self.performance_metrics[key]) > 100:
                self.performance_metrics[key] = self.performance_metrics[key][-50:]

    def get_autonomy_report(self) -> dict[str, Any]:
        """Get a comprehensive report on autonomy system status."""
        return {
            "total_decisions": len(self.decision_history),
            "strategic_goals": self.strategic_goals,
            "memory_stats": self.memory.get_memory_stats(),
            "performance_metrics": self.performance_metrics,
            "recent_decisions": self.decision_history[-5:],
            "decision_types": {
                dt.value: sum(1 for d in self.decision_history if d.decision_type == dt)
                for dt in DecisionType
            },
        }
