"""
Advanced Metacognition and Self-Reflection System

This system implements sophisticated self-awareness and metacognitive capabilities
designed specifically for AI cognition, not human imitation:

1. **Multi-level Self-Awareness**: Monitor cognitive processes, decision patterns, and knowledge states
2. **Strategic Reflection**: Purposeful reflection aimed at optimization and growth
3. **Meta-Learning**: Learn how to learn more effectively
4. **Cognitive Architecture Awareness**: Understand and optimize own cognitive processes
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pmm.autonomy.enhanced_autonomy import EnhancedAutonomy
from pmm.memory.cognitive_memory import CognitiveMemory, MemoryTier
from pmm.storage.eventlog import EventLog

logger = logging.getLogger(__name__)


class ReflectionType(Enum):
    PERFORMANCE = "performance"  # Reflect on performance metrics
    STRATEGIC = "strategic"  # Reflect on goal alignment and strategy
    COGNITIVE = "cognitive"  # Reflect on thinking processes
    LEARNING = "learning"  # Reflect on knowledge acquisition
    DECISION = "decision"  # Reflect on decision quality
    IDENTITY = "identity"  # Reflect on identity and self-concept


class MetacognitiveLevel(Enum):
    OBJECT = "object"  # Thinking about thoughts/content
    STRATEGY = "strategy"  # Thinking about thinking methods
    MONITORING = "monitoring"  # Monitoring cognitive processes
    CONTROL = "control"  # Controlling cognitive processes


@dataclass
class ReflectionTrigger:
    """Conditions that trigger reflective processes."""

    trigger_type: str
    threshold: float
    current_value: float
    urgency: float  # 0-1 scale
    description: str


@dataclass
class MetacognitiveInsight:
    """An insight gained through metacognitive reflection."""

    insight_type: ReflectionType
    content: str
    confidence: float
    actionable: bool
    priority: int
    expected_impact: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class CognitiveState:
    """Current state of cognitive processes."""

    working_memory_load: float  # 0-1 scale
    attention_focus: list[str]
    processing_speed: float  # Relative to baseline
    error_rate: float  # Recent error frequency
    confidence_level: float  # Overall confidence in outputs
    knowledge_gaps: list[str]
    cognitive_biases: list[str]


class MetaReflector:
    """
    Advanced metacognition system for AI self-awareness and optimization.

    This system goes beyond simple reflection to implement true metacognitive
    monitoring and control of cognitive processes.
    """

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog
        self.memory = CognitiveMemory(eventlog)
        self.autonomy = EnhancedAutonomy(eventlog)
        self.reflection_history: list[MetacognitiveInsight] = []
        self.cognitive_state = CognitiveState(
            working_memory_load=0.0,
            attention_focus=[],
            processing_speed=1.0,
            error_rate=0.0,
            confidence_level=0.8,
            knowledge_gaps=[],
            cognitive_biases=[],
        )
        self.metacognitive_skills: dict[str, float] = {}
        self.learning_strategies: list[str] = []

    def initialize(self) -> None:
        """Initialize the metacognition system."""
        logger.info("Initializing metacognition system...")
        self.memory.build_memory_index()
        self.autonomy.initialize()
        self._establish_baseline()
        self._initialize_metacognitive_skills()

    def monitor_cognitive_state(self) -> CognitiveState:
        """Monitor current cognitive state and update internal model."""
        # Monitor working memory load
        active_memories = self.memory.query(
            "current active working memory",
            tier_filter=MemoryTier.ACTIVE,
            max_results=20,
        )
        self.cognitive_state.working_memory_load = min(len(active_memories) / 20.0, 1.0)

        # Monitor attention focus
        recent_queries = self.memory.query(
            "recent attention focus topics", max_results=5
        )
        self.cognitive_state.attention_focus = [m.content[:50] for m in recent_queries]

        # Monitor processing speed (simplified)
        recent_reflections = self.memory.query(
            "reflection processing time", max_results=10
        )
        if recent_reflections:
            # Simplified speed calculation
            self.cognitive_state.processing_speed = 1.0  # Would calculate actual speed

        # Monitor error rate
        error_memories = self.memory.query("error mistake failure", max_results=10)
        total_recent = self.memory.query("recent activities", max_results=50)
        if total_recent:
            self.cognitive_state.error_rate = len(error_memories) / len(total_recent)

        # Monitor confidence level
        confidence_memories = self.memory.query(
            "confidence certainty sure", max_results=10
        )
        if confidence_memories:
            # Extract confidence values (simplified)
            self.cognitive_state.confidence_level = (
                0.8  # Would calculate actual confidence
            )

        # Identify knowledge gaps
        gap_memories = self.memory.query("don't know uncertain unclear", max_results=5)
        self.cognitive_state.knowledge_gaps = [m.content[:100] for m in gap_memories]

        # Identify cognitive biases
        bias_patterns = self._identify_cognitive_biases()
        self.cognitive_state.cognitive_biases = bias_patterns

        return self.cognitive_state

    def should_reflect(self) -> tuple[bool, ReflectionTrigger | None]:
        """Determine if reflection should be triggered and why."""
        triggers = self._identify_reflection_triggers()

        if not triggers:
            return False, None

        # Select most urgent trigger
        triggers.sort(key=lambda t: t.urgency, reverse=True)
        return True, triggers[0]

    def _identify_reflection_triggers(self) -> list[ReflectionTrigger]:
        """Identify conditions that should trigger reflection."""
        triggers = []

        # Performance-based triggers
        current_state = self.monitor_cognitive_state()

        if current_state.error_rate > 0.2:
            triggers.append(
                ReflectionTrigger(
                    trigger_type="high_error_rate",
                    threshold=0.2,
                    current_value=current_state.error_rate,
                    urgency=0.8,
                    description=f"Error rate ({current_state.error_rate:.2f}) exceeds threshold",
                )
            )

        if current_state.confidence_level < 0.5:
            triggers.append(
                ReflectionTrigger(
                    trigger_type="low_confidence",
                    threshold=0.5,
                    current_value=current_state.confidence_level,
                    urgency=0.7,
                    description=f"Confidence level ({current_state.confidence_level:.2f}) below threshold",
                )
            )

        if current_state.working_memory_load > 0.8:
            triggers.append(
                ReflectionTrigger(
                    trigger_type="cognitive_overload",
                    threshold=0.8,
                    current_value=current_state.working_memory_load,
                    urgency=0.6,
                    description=f"Working memory load ({current_state.working_memory_load:.2f}) too high",
                )
            )

        # Time-based triggers
        last_reflection = (
            self.reflection_history[-1] if self.reflection_history else None
        )
        if (
            not last_reflection or time.time() - last_reflection.timestamp > 3600
        ):  # 1 hour
            triggers.append(
                ReflectionTrigger(
                    trigger_type="periodic_reflection",
                    threshold=3600,
                    current_value=time.time()
                    - (last_reflection.timestamp if last_reflection else 0),
                    urgency=0.3,
                    description="Periodic reflection due",
                )
            )

        # Decision-based triggers
        recent_decisions = self.autonomy.decision_history[-5:]
        if recent_decisions:
            avg_confidence = sum(d.confidence for d in recent_decisions) / len(
                recent_decisions
            )
            if avg_confidence < 0.6:
                triggers.append(
                    ReflectionTrigger(
                        trigger_type="low_decision_confidence",
                        threshold=0.6,
                        current_value=avg_confidence,
                        urgency=0.5,
                        description="Recent decision confidence below threshold",
                    )
                )

        return triggers

    def engage_reflection(
        self, trigger: ReflectionTrigger
    ) -> list[MetacognitiveInsight]:
        """Engage in reflective process based on trigger."""
        logger.info(f"Engaging reflection due to: {trigger.description}")

        insights = []

        # Select appropriate reflection type based on trigger
        if trigger.trigger_type in ["high_error_rate", "low_confidence"]:
            insights.extend(self._performance_reflection(trigger))
        elif trigger.trigger_type == "cognitive_overload":
            insights.extend(self._cognitive_reflection(trigger))
        elif trigger.trigger_type == "periodic_reflection":
            insights.extend(self._strategic_reflection(trigger))
        elif trigger.trigger_type == "low_decision_confidence":
            insights.extend(self._decision_reflection(trigger))
        else:
            insights.extend(self._general_reflection(trigger))

        # Store insights
        self.reflection_history.extend(insights)

        # Update metacognitive skills based on reflection
        self._update_metacognitive_skills(insights)

        return insights

    def _performance_reflection(
        self, trigger: ReflectionTrigger
    ) -> list[MetacognitiveInsight]:
        """Reflect on performance issues."""
        insights = []

        # Analyze recent performance
        performance_memories = self.memory.query(
            "performance metrics success failure achievement",
            max_results=15,
            min_relevance=0.3,
        )

        # Look for patterns in performance data
        if "error" in trigger.trigger_type:
            insights.append(
                MetacognitiveInsight(
                    insight_type=ReflectionType.PERFORMANCE,
                    content=(
                        f"High error rate detected ({trigger.current_value:.2f}). "
                        "Need to analyze error patterns and implement corrective strategies."
                    ),
                    confidence=0.8,
                    actionable=True,
                    priority=1,
                    expected_impact="Reduce error rate through pattern analysis and strategy adjustment",
                )
            )

        # Identify specific areas for improvement
        weak_areas = self._identify_performance_weaknesses(performance_memories)
        for area in weak_areas:
            insights.append(
                MetacognitiveInsight(
                    insight_type=ReflectionType.PERFORMANCE,
                    content=f"Performance weakness identified in {area}. Targeted improvement needed.",
                    confidence=0.7,
                    actionable=True,
                    priority=2,
                    expected_impact=f"Improve {area} performance through focused practice",
                )
            )

        return insights

    def _cognitive_reflection(
        self, trigger: ReflectionTrigger
    ) -> list[MetacognitiveInsight]:
        """Reflect on cognitive processes."""
        insights = []

        current_state = self.monitor_cognitive_state()

        if current_state.working_memory_load > 0.8:
            insights.append(
                MetacognitiveInsight(
                    insight_type=ReflectionType.COGNITIVE,
                    content=(
                        "Working memory overload detected. Need to implement better "
                        "information filtering and prioritization."
                    ),
                    confidence=0.9,
                    actionable=True,
                    priority=1,
                    expected_impact="Reduce cognitive load through better memory management",
                )
            )

        # Analyze attention patterns
        if len(current_state.attention_focus) > 5:
            insights.append(
                MetacognitiveInsight(
                    insight_type=ReflectionType.COGNITIVE,
                    content=(
                        "Attention appears scattered across multiple topics. "
                        "Consider focusing on fewer concurrent objectives."
                    ),
                    confidence=0.7,
                    actionable=True,
                    priority=2,
                    expected_impact="Improve focus and task completion through attention consolidation",
                )
            )

        return insights

    def _strategic_reflection(
        self, trigger: ReflectionTrigger
    ) -> list[MetacognitiveInsight]:
        """Reflect on strategic alignment and goals."""
        insights = []

        # Review strategic goals
        goals = self.autonomy.strategic_goals
        recent_activities = self.memory.query(
            "recent work activities progress", max_results=20
        )

        if not goals:
            insights.append(
                MetacognitiveInsight(
                    insight_type=ReflectionType.STRATEGIC,
                    content="No strategic goals defined. Need to establish clear objectives for better direction.",
                    confidence=0.9,
                    actionable=True,
                    priority=1,
                    expected_impact="Provide clear direction and purpose for activities",
                )
            )
        else:
            # Check goal alignment
            alignment_score = self._calculate_goal_alignment(goals, recent_activities)
            if alignment_score < 0.5:
                insights.append(
                    MetacognitiveInsight(
                        insight_type=ReflectionType.STRATEGIC,
                        content=(
                            f"Poor strategic alignment detected (score: {alignment_score:.2f}). "
                            "Activities not supporting strategic goals."
                        ),
                        confidence=0.8,
                        actionable=True,
                        priority=2,
                        expected_impact="Improve effectiveness through better strategic alignment",
                    )
                )

        return insights

    def _decision_reflection(
        self, trigger: ReflectionTrigger
    ) -> list[MetacognitiveInsight]:
        """Reflect on decision-making processes."""
        insights = []

        recent_decisions = self.autonomy.decision_history[-10:]

        if not recent_decisions:
            return insights

        # Analyze decision patterns
        avg_confidence = sum(d.confidence for d in recent_decisions) / len(
            recent_decisions
        )
        decision_types = [d.decision_type.value for d in recent_decisions]

        insights.append(
            MetacognitiveInsight(
                insight_type=ReflectionType.DECISION,
                content=(
                    f"Recent decision confidence averaging {avg_confidence:.2f}. "
                    f"Decision patterns: {decision_types}"
                ),
                confidence=0.7,
                actionable=True,
                priority=2,
                expected_impact="Improve decision quality through pattern analysis",
            )
        )

        # Look for decision biases
        biases = self._identify_decision_biases(recent_decisions)
        for bias in biases:
            insights.append(
                MetacognitiveInsight(
                    insight_type=ReflectionType.DECISION,
                    content=f"Potential decision bias detected: {bias}. Need to implement debiasing strategies.",
                    confidence=0.6,
                    actionable=True,
                    priority=3,
                    expected_impact="Reduce bias in decision-making process",
                )
            )

        return insights

    def _general_reflection(
        self, trigger: ReflectionTrigger
    ) -> list[MetacognitiveInsight]:
        """General reflection for unspecified triggers."""
        insights = []

        # Comprehensive self-assessment
        current_state = self.monitor_cognitive_state()

        insights.append(
            MetacognitiveInsight(
                insight_type=ReflectionType.IDENTITY,
                content=f"General self-assessment: cognitive load {current_state.working_memory_load:.2f}, "
                f"confidence {current_state.confidence_level:.2f}, error rate {current_state.error_rate:.2f}",
                confidence=0.8,
                actionable=False,
                priority=5,
                expected_impact="Maintain self-awareness of cognitive state",
            )
        )

        return insights

    def _identify_performance_weaknesses(self, memories: list) -> list[str]:
        """Identify specific areas of performance weakness."""
        weaknesses = []

        # Simplified weakness identification
        memory_contents = " ".join(m.content.lower() for m in memories)

        if "commitment" in memory_contents and "fail" in memory_contents:
            weaknesses.append("commitment_execution")
        if "reflect" in memory_contents and "superficial" in memory_contents:
            weaknesses.append("reflection_depth")
        if "decision" in memory_contents and "poor" in memory_contents:
            weaknesses.append("decision_quality")

        return weaknesses

    def _calculate_goal_alignment(self, goals: list[str], activities: list) -> float:
        """Calculate how well recent activities align with strategic goals."""
        if not goals:
            return 0.0

        alignment_scores = []
        for goal in goals:
            goal_memories = self.memory.query(goal, max_results=10)
            alignment_scores.append(len(goal_memories))

        return sum(alignment_scores) / (len(goals) * 10)  # Normalize to 0-1

    def _identify_decision_biases(self, decisions: list) -> list[str]:
        """Identify potential biases in decision-making patterns."""
        biases = []

        # Simplified bias detection
        decision_types = [d.decision_type.value for d in decisions]

        # Check for over-reliance on certain decision types
        from collections import Counter

        type_counts = Counter(decision_types)
        for decision_type, count in type_counts.items():
            if count > len(decisions) * 0.6:  # More than 60% of one type
                biases.append(f"overreliance_on_{decision_type}")

        return biases

    def _identify_cognitive_biases(self) -> list[str]:
        """Identify cognitive biases in thinking patterns."""
        biases = []

        # Look for bias patterns in memory
        bias_memories = self.memory.query(
            "bias assumption prejudice stereotype", max_results=5
        )

        # Simplified bias identification
        for memory in bias_memories:
            content = memory.content.lower()
            if "always" in content or "never" in content:
                biases.append("absolute_thinking")
            if "confirm" in content and "belief" in content:
                biases.append("confirmation_bias")

        return biases

    def _establish_baseline(self) -> None:
        """Establish baseline cognitive performance metrics."""
        # This would analyze historical performance to set baselines
        logger.info("Establishing cognitive baseline...")

    def _initialize_metacognitive_skills(self) -> None:
        """Initialize metacognitive skill tracking."""
        self.metacognitive_skills = {
            "self_monitoring": 0.7,
            "self_evaluation": 0.6,
            "strategic_planning": 0.5,
            "cognitive_flexibility": 0.8,
            "metacognitive_awareness": 0.7,
        }

    def _update_metacognitive_skills(
        self, insights: list[MetacognitiveInsight]
    ) -> None:
        """Update metacognitive skills based on reflection insights."""
        # Simplified skill updating
        for insight in insights:
            if insight.insight_type == ReflectionType.COGNITIVE:
                self.metacognitive_skills["self_monitoring"] = min(
                    self.metacognitive_skills["self_monitoring"] + 0.01, 1.0
                )
            elif insight.insight_type == ReflectionType.PERFORMANCE:
                self.metacognitive_skills["self_evaluation"] = min(
                    self.metacognitive_skills["self_evaluation"] + 0.01, 1.0
                )

    def get_metacognitive_report(self) -> dict[str, Any]:
        """Get comprehensive metacognitive system report."""
        current_state = self.monitor_cognitive_state()

        return {
            "cognitive_state": {
                "working_memory_load": current_state.working_memory_load,
                "attention_focus": current_state.attention_focus,
                "processing_speed": current_state.processing_speed,
                "error_rate": current_state.error_rate,
                "confidence_level": current_state.confidence_level,
                "knowledge_gaps": current_state.knowledge_gaps,
                "cognitive_biases": current_state.cognitive_biases,
            },
            "metacognitive_skills": self.metacognitive_skills,
            "reflection_history_size": len(self.reflection_history),
            "recent_insights": [
                {
                    "type": insight.insight_type.value,
                    "content": (
                        insight.content[:100] + "..."
                        if len(insight.content) > 100
                        else insight.content
                    ),
                    "confidence": insight.confidence,
                    "priority": insight.priority,
                }
                for insight in self.reflection_history[-5:]
            ],
            "learning_strategies": self.learning_strategies,
        }
