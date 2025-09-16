import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import defaultdict, Counter

try:
    from pmm.storage.eventlog import EventLog
    from pmm.directives.hierarchy import (
        DirectiveHierarchy,
        Directive,
        MetaPrinciple,
        Principle,
        Commitment,
    )
except ImportError:
    EventLog = None
    DirectiveHierarchy = None
    Directive = None
    MetaPrinciple = None
    Principle = None
    Commitment = None

logger = logging.getLogger(__name__)


@dataclass
class ContinuityInsight:
    """Represents a detected pattern of continuity or drift in commitments."""

    insight_type: str  # 'reinforcement', 'drift', 'emergence', 'consolidation'
    confidence: float
    description: str
    supporting_directives: List[str]  # directive IDs
    timespan_days: int
    created_at: datetime

    def to_commitment_text(self) -> str:
        """Convert this insight into a commitment statement."""
        if self.insight_type == "reinforcement":
            return f"I consistently reinforce {self.description} across my interactions, maintaining this as a core aspect of my identity."
        elif self.insight_type == "emergence":
            return f"I recognize an emerging pattern in my commitments: {self.description}. This represents a natural evolution of my principles."
        elif self.insight_type == "consolidation":
            return f"I observe that my various commitments are consolidating around {self.description}, indicating a maturing coherence in my approach."
        elif self.insight_type == "drift":
            return f"I acknowledge a shift in my commitments toward {self.description}, representing adaptive growth while maintaining core principles."
        else:
            return f"I recognize a continuity pattern: {self.description}"


class ContinuityEngine:
    """
    Analyzes commitment patterns over time to detect coherence, drift, and emergent identity.
    This engine periodically reflects on the PMM's commitment history to:
    1. Detect reinforcement patterns (consistent themes)
    2. Identify adaptive drift (evolution while maintaining core)
    3. Recognize emergent consolidation (scattered commitments coalescing)
    4. Auto-register continuity insights as permanent commitments
    """

    def __init__(
        self,
        eventlog: Optional["EventLog"] = None,
        hierarchy: Optional["DirectiveHierarchy"] = None,
    ):
        self.eventlog = eventlog
        self.hierarchy = hierarchy
        self.last_reflection = None
        self.reflection_cooldown_hours = 6  # Minimum time between reflections

    def should_reflect(self) -> bool:
        """Determine if it's time for a continuity reflection."""
        if self.last_reflection is None:
            return True

        time_since_last = datetime.now(timezone.utc) - self.last_reflection
        return time_since_last > timedelta(hours=self.reflection_cooldown_hours)

    def analyze_continuity(self, lookback_days: int = 30) -> List[ContinuityInsight]:
        """
        Analyze commitment patterns over the specified timeframe.
        Returns insights about reinforcement, drift, emergence, and consolidation.
        Logs analysis process to EventLog.
        """
        logger.info(f"Analyzing continuity patterns over {lookback_days} days")

        if self.eventlog:
            self.eventlog.append(
                kind="continuity_analysis_started",
                content="",
                meta={"lookback_days": lookback_days},
            )

        # Get recent directives
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        recent_directives = self._get_directives_since(cutoff_date)

        if len(recent_directives) < 3:
            logger.info("Insufficient directives for continuity analysis")
            if self.eventlog:
                self.eventlog.append(
                    kind="continuity_analysis_skipped",
                    content="",
                    meta={
                        "reason": "insufficient directives",
                        "count": len(recent_directives),
                    },
                )
            return []

        insights = []

        # 1. Detect reinforcement patterns
        insights.extend(
            self._detect_reinforcement_patterns(recent_directives, lookback_days)
        )

        # 2. Detect emergent themes
        insights.extend(self._detect_emergent_themes(recent_directives, lookback_days))

        # 3. Detect consolidation patterns
        insights.extend(
            self._detect_consolidation_patterns(recent_directives, lookback_days)
        )

        # 4. Detect adaptive drift
        insights.extend(self._detect_adaptive_drift(recent_directives, lookback_days))

        if self.eventlog:
            self.eventlog.append(
                kind="continuity_analysis_completed",
                content="",
                meta={"insight_count": len(insights)},
            )

        return insights

    def _get_directives_since(self, cutoff_date: datetime) -> List["Directive"]:
        """Get all directives created since the cutoff date from EventLog."""
        if not self.eventlog or not self.hierarchy:
            return []

        directives = []
        events = self.eventlog.query(kind="directive_added")
        for event in events:
            try:
                created_at = datetime.fromisoformat(
                    event.meta.get("created_at", "").replace("Z", "")
                )
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at >= cutoff_date:
                    directive_id = event.meta.get("id", "")
                    directive_type = event.meta.get("type", "")
                    content = event.content
                    if directive_type == "meta-principle":
                        directives.append(
                            MetaPrinciple(
                                id=directive_id,
                                content=content,
                                created_at=event.meta.get("created_at", ""),
                                source_event_id=event.meta.get("source_event_id", None),
                                confidence=float(event.meta.get("confidence", 0.0)),
                                triggers_evolution=event.meta.get(
                                    "triggers_evolution", True
                                ),
                                evolution_scope=event.meta.get(
                                    "evolution_scope", "framework"
                                ),
                            )
                        )
                    elif directive_type == "principle":
                        directives.append(
                            Principle(
                                id=directive_id,
                                content=content,
                                created_at=event.meta.get("created_at", ""),
                                source_event_id=event.meta.get("source_event_id", None),
                                confidence=float(event.meta.get("confidence", 0.0)),
                                parent_meta_principle=event.meta.get(
                                    "parent_meta_principle", None
                                ),
                                permanence_level=event.meta.get(
                                    "permanence_level", "high"
                                ),
                            )
                        )
                    else:  # commitment
                        directives.append(
                            Commitment(
                                id=directive_id,
                                content=content,
                                created_at=event.meta.get("created_at", ""),
                                source_event_id=event.meta.get("source_event_id", None),
                                confidence=float(event.meta.get("confidence", 0.0)),
                                parent_principle=event.meta.get(
                                    "parent_principle", None
                                ),
                                behavioral_scope=event.meta.get(
                                    "behavioral_scope", "specific"
                                ),
                            )
                        )
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                continue

        return directives

    def _detect_reinforcement_patterns(
        self, directives: List["Directive"], timespan_days: int
    ) -> List[ContinuityInsight]:
        """Detect patterns of reinforcement in directives over the timespan."""
        if not directives:
            return []

        # Group directives by content themes (simple word overlap for now)
        theme_counts = defaultdict(list)
        for d in directives:
            if d.directive_type == "commitment":
                words = set(d.content.lower().split())
                for w in words:
                    if len(w) > 3:  # Ignore short words
                        theme_counts[w].append(d)

        insights = []
        for theme, theme_directives in theme_counts.items():
            if len(theme_directives) >= 3:  # Minimum threshold for reinforcement
                confidence = min(1.0, 0.5 + (len(theme_directives) * 0.1))
                insights.append(
                    ContinuityInsight(
                        insight_type="reinforcement",
                        confidence=confidence,
                        description=f"commitments around '{theme}'",
                        supporting_directives=[d.id for d in theme_directives],
                        timespan_days=timespan_days,
                        created_at=datetime.now(timezone.utc),
                    )
                )

        return insights

    def _detect_emergent_themes(
        self, directives: List["Directive"], timespan_days: int
    ) -> List[ContinuityInsight]:
        """Detect emergent themes in recent directives."""
        if not directives:
            return []

        # Simple emergent theme detection based on recent principles
        recent_principles = [d for d in directives if d.directive_type == "principle"]
        if len(recent_principles) < 2:
            return []

        insights = []
        # Group by time clusters (within a week)
        time_clusters = defaultdict(list)
        for p in recent_principles:
            try:
                created_at = datetime.fromisoformat(p.created_at.replace("Z", ""))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                week_start = created_at - timedelta(days=created_at.weekday())
                time_clusters[week_start].append(p)
            except Exception:
                continue

        for week, cluster in time_clusters.items():
            if len(cluster) >= 2:  # At least 2 principles in a short time frame
                confidence = min(1.0, 0.4 + (len(cluster) * 0.15))
                common_words = self._find_common_words([p.content for p in cluster])
                if common_words:
                    description = f"principles related to {', '.join(common_words[:3])}"
                    insights.append(
                        ContinuityInsight(
                            insight_type="emergence",
                            confidence=confidence,
                            description=description,
                            supporting_directives=[p.id for p in cluster],
                            timespan_days=timespan_days,
                            created_at=datetime.now(timezone.utc),
                        )
                    )

        return insights

    def _detect_consolidation_patterns(
        self, directives: List["Directive"], timespan_days: int
    ) -> List[ContinuityInsight]:
        """Detect patterns of consolidation across different directive types."""
        if not directives or not self.hierarchy:
            return []

        relationships = self.hierarchy.get_directive_relationships()
        insights = []

        # Look for principles with multiple commitments
        for principle_id, commitment_ids in relationships[
            "principle_to_commitments"
        ].items():
            if len(commitment_ids) >= 3:  # Minimum threshold for consolidation
                principle = next((p for p in directives if p.id == principle_id), None)
                if principle:
                    confidence = min(1.0, 0.5 + (len(commitment_ids) * 0.1))
                    insights.append(
                        ContinuityInsight(
                            insight_type="consolidation",
                            confidence=confidence,
                            description=f"commitments under principle '{principle.content[:50]}...'",
                            supporting_directives=[principle_id] + commitment_ids,
                            timespan_days=timespan_days,
                            created_at=datetime.now(timezone.utc),
                        )
                    )

        return insights

    def _detect_adaptive_drift(
        self, directives: List["Directive"], timespan_days: int
    ) -> List[ContinuityInsight]:
        """Detect adaptive drift by comparing older and newer directives."""
        if not directives:
            return []

        # Split directives into older and newer halves based on creation date
        sorted_directives = sorted(
            directives,
            key=lambda d: (
                datetime.fromisoformat(d.created_at.replace("Z", ""))
                if d.created_at
                else datetime.now(timezone.utc)
            ),
        )
        midpoint = len(sorted_directives) // 2
        older = sorted_directives[:midpoint]
        newer = sorted_directives[midpoint:]

        if not older or not newer:
            return []

        # Simple comparison of themes (word frequency shift)
        older_themes = self._extract_themes(older)
        newer_themes = self._extract_themes(newer)

        insights = []
        for theme in newer_themes:
            if (
                theme not in older_themes
                or newer_themes[theme] > older_themes.get(theme, 0) * 1.5
            ):
                confidence = min(1.0, 0.4 + (newer_themes[theme] * 0.1))
                insights.append(
                    ContinuityInsight(
                        insight_type="drift",
                        confidence=confidence,
                        description=f"increasing focus on '{theme}' in recent commitments",
                        supporting_directives=[
                            d.id for d in newer if theme in d.content.lower()
                        ],
                        timespan_days=timespan_days,
                        created_at=datetime.now(timezone.utc),
                    )
                )

        return insights

    def _extract_themes(self, directives: List["Directive"]) -> Dict[str, int]:
        """Extract common themes from directives based on word frequency."""
        word_freq = Counter()
        for d in directives:
            words = d.content.lower().split()
            for w in words:
                if len(w) > 3:  # Ignore short words
                    word_freq[w] += 1

        return {word: freq for word, freq in word_freq.items() if freq > 1}

    def _find_common_words(self, texts: List[str]) -> List[str]:
        """Find common words across a list of texts."""
        if not texts:
            return []

        word_sets = [set(text.lower().split()) for text in texts]
        common = set.intersection(*word_sets) if word_sets else set()
        return [w for w in common if len(w) > 3]  # Ignore short words

    def reflect_and_register(self, insights: List[ContinuityInsight]) -> List[str]:
        """
        Register insights as permanent commitments if they meet confidence thresholds.
        Updates last_reflection timestamp.
        Logs registration to EventLog.
        """
        if not self.hierarchy:
            return []

        registered_ids = []
        for insight in insights:
            if insight.confidence >= 0.7:  # Confidence threshold for registration
                commitment_text = insight.to_commitment_text()
                directive = self.hierarchy.add_directive(commitment_text)
                if directive:
                    registered_ids.append(directive.id)
                    if self.eventlog:
                        self.eventlog.append(
                            kind="continuity_insight_registered",
                            content=commitment_text,
                            meta={
                                "insight_type": insight.insight_type,
                                "confidence": insight.confidence,
                                "directive_id": directive.id,
                            },
                        )

        self.last_reflection = datetime.now(timezone.utc)
        return registered_ids


# Ensure proper statement separation with multiple newlines at the end of the file
