"""
Synthesis engine for proactive pattern discovery and hypothesis generation.

Phase 3 component that analyzes recent events to discover patterns
and generate testable hypotheses about system behavior.
"""

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from pmm.runtime.hypothesis_tracker import HypothesisTracker
from pmm.runtime.memegraph import MemeGraphProjection
from pmm.storage.eventlog import EventLog


@dataclass
class PatternCandidate:
    """Candidate pattern discovered by synthesis engine."""

    pattern_type: str  # "co_occurrence", "semantic_cluster", "outcome_correlation"
    description: str
    confidence: float  # 0-1
    evidence_tokens: list[str]  # [id:digest] citations
    suggested_hypothesis: str  # "If X then Y within Z measured by M"
    supporting_events: list[int]  # Event IDs that support this pattern


@dataclass
class SynthesisSnapshot:
    """Snapshot of synthesis analysis for audit trail."""

    timestamp: str
    inputs: dict[str, Any]  # What was analyzed
    patterns: list[PatternCandidate]  # Discovered patterns
    candidates: list[str]  # Top hypothesis candidates
    metadata: dict[str, Any]  # Additional context


class SynthesisEngine:
    """
    Deterministic pattern detection and hypothesis generation.

    Scans multiple data sources to find cross-event patterns that could
    form the basis for testable hypotheses.
    """

    def __init__(
        self, eventlog: EventLog, memegraph: MemeGraphProjection, seed: int = 42
    ):
        self.eventlog = eventlog
        self.memegraph = memegraph
        self.seed = seed
        self._deterministic_counter = 0

    def _deterministic_hash(self, input_data: str) -> float:
        """Generate deterministic float for consistent ordering."""
        combined = f"{self.seed}:{self._deterministic_counter}:{input_data}"
        hash_obj = hashlib.sha256(combined.encode())
        self._deterministic_counter += 1

        hash_int = int(hash_obj.hexdigest()[:8], 16)
        return hash_int / 0xFFFFFFFF

    def run_synthesis(
        self,
        window_size: int = 100,
        min_pattern_support: int = 3,
        max_candidates: int = 5,
    ) -> SynthesisSnapshot:
        """
        Run complete synthesis analysis on recent ledger data.

        Args:
            window_size: Number of recent events to analyze
            min_pattern_support: Minimum evidence count for patterns
            max_candidates: Maximum hypothesis candidates to generate

        Returns:
            SynthesisSnapshot with all discovered patterns and candidates
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Get recent events for analysis
        recent_events = self.eventlog.read_tail(limit=window_size)

        # Run different pattern detection algorithms
        patterns = []

        # 1. Co-occurrence patterns in events
        co_occurrence_patterns = self._detect_co_occurrence_patterns(
            recent_events, min_pattern_support
        )
        patterns.extend(co_occurrence_patterns)

        # 2. MemeGraph structural patterns
        graph_patterns = self._detect_graph_patterns(min_pattern_support)
        patterns.extend(graph_patterns)

        # 3. Outcome correlation patterns
        outcome_patterns = self._detect_outcome_correlations(
            recent_events, min_pattern_support
        )
        patterns.extend(outcome_patterns)

        # Sort patterns by confidence (deterministic)
        patterns.sort(
            key=lambda p: (p.confidence, self._deterministic_counter), reverse=True
        )

        # Generate top hypothesis candidates
        candidates = [
            p.suggested_hypothesis
            for p in patterns[:max_candidates]
            if p.suggested_hypothesis
        ]

        return SynthesisSnapshot(
            timestamp=timestamp,
            inputs={
                "window_size": window_size,
                "event_count": len(recent_events),
                "min_support": min_pattern_support,
            },
            patterns=patterns,
            candidates=candidates,
            metadata={
                "pattern_types": list(set(p.pattern_type for p in patterns)),
                "total_evidence_tokens": sum(len(p.evidence_tokens) for p in patterns),
                "analysis_seed": self.seed,
            },
        )

    def _detect_co_occurrence_patterns(
        self, events: list[dict[str, Any]], min_support: int
    ) -> list[PatternCandidate]:
        """
        Detect patterns where specific terms or concepts co-occur frequently.

        Args:
            events: List of events to analyze
            min_support: Minimum co-occurrence count

        Returns:
            List of co-occurrence pattern candidates
        """
        patterns = []

        # Extract terms from event content
        term_events = defaultdict(list)
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "me",
            "him",
            "her",
            "us",
            "them",
        }

        for event in events:
            content = event.get("content", "").lower()

            # Extract words with 3+ characters deterministically
            words = []
            current_word = []
            for char in content:
                if char.isalpha():
                    current_word.append(char)
                else:
                    if current_word and len(current_word) >= 3:
                        words.append("".join(current_word))
                    current_word = []
            # Check last word
            if current_word and len(current_word) >= 3:
                words.append("".join(current_word))

            for word in words:
                if word not in stop_words:
                    term_events[word].append(event["id"])

        # Find co-occurring terms
        term_pairs = []
        for term1, events1 in term_events.items():
            for term2, events2 in term_events.items():
                if term1 < term2:  # Avoid duplicates
                    common_events = set(events1) & set(events2)
                    if len(common_events) >= min_support:
                        term_pairs.append((term1, term2, common_events))

        # Generate patterns from co-occurrences
        for term1, term2, common_events in term_pairs:
            confidence = min(1.0, len(common_events) / 10.0)  # Normalize confidence

            # Generate evidence tokens
            evidence_tokens = []
            for event_id in common_events:
                try:
                    digest = self.memegraph.event_digest(event_id)
                    evidence_tokens.append(f"[{event_id}:{digest[:8]}]")
                except Exception:
                    continue

            # Generate hypothesis suggestion
            hypothesis = (
                f"If discussions mention '{term1}' then they also mention '{term2}' "
                f"within 5 events measured by co_occurrence"
            )

            pattern = PatternCandidate(
                pattern_type="co_occurrence",
                description=f"Terms '{term1}' and '{term2}' co-occur in {len(common_events)} events",
                confidence=confidence,
                evidence_tokens=evidence_tokens[:10],  # Limit tokens
                suggested_hypothesis=hypothesis,
                supporting_events=list(common_events),
            )

            patterns.append(pattern)

        return patterns

    def _detect_graph_patterns(self, min_support: int) -> list[PatternCandidate]:
        """
        Detect patterns in MemeGraph structure (clusters, bridges, etc.).

        Args:
            min_support: Minimum node/edge count for patterns

        Returns:
            List of graph pattern candidates
        """
        patterns = []

        try:
            # Get graph statistics
            nodes = self.memegraph.get_all_nodes()
            edges = self.memegraph.get_all_edges()

            # Group nodes by type
            node_types = defaultdict(list)
            for node in nodes:
                node_type = node.get("type", "unknown")
                node_types[node_type].append(node)

            # Look for interesting structural patterns
            for node_type, type_nodes in node_types.items():
                if len(type_nodes) >= min_support:
                    # Find highly connected nodes in this type
                    node_connections = defaultdict(int)

                    for edge in edges:
                        source = edge.get("source")
                        target = edge.get("target")

                        if source in [n.get("id") for n in type_nodes]:
                            node_connections[source] += 1
                        if target in [n.get("id") for n in type_nodes]:
                            node_connections[target] += 1

                    # Find most connected nodes
            if node_connections:
                most_connected = max(node_connections.items(), key=lambda x: x[1])
                node_id, connection_count = most_connected

                if connection_count >= min_support:
                    # Get the node details
                    node_details = next(
                        (n for n in type_nodes if n.get("id") == node_id), {}
                    )
                    node_content = node_details.get("content", "").lower()[:50]

                    # Generate evidence tokens
                    evidence_tokens = []
                    try:
                        digest = self.memegraph.event_digest(node_id)
                        evidence_tokens.append(f"[{node_id}:{digest[:8]}]")
                    except Exception:
                        pass

                    hypothesis = (
                        f"If content involves '{node_content}' then it creates high "
                        f"connectivity within the knowledge graph measured by edge_count"
                    )

                    pattern = PatternCandidate(
                        pattern_type="graph_structure",
                        description=f"Highly connected {node_type} node with {connection_count} connections",
                        confidence=min(1.0, connection_count / 20.0),
                        evidence_tokens=evidence_tokens,
                        suggested_hypothesis=hypothesis,
                        supporting_events=[node_id],
                    )

                    patterns.append(pattern)

        except Exception:
            # Graph analysis failures should not break synthesis
            pass

        return patterns

    def _detect_outcome_correlations(
        self, events: list[dict[str, Any]], min_support: int
    ) -> list[PatternCandidate]:
        """
        Detect correlations between actions and outcomes.

        Args:
            events: List of events to analyze
            min_support: Minimum correlation count

        Returns:
            List of outcome correlation pattern candidates
        """
        patterns = []

        # Look for commitment -> outcome patterns
        commitments = [e for e in events if e.get("kind") == "commitment_open"]
        reflections = [e for e in events if e.get("kind") == "reflection"]

        if len(commitments) < min_support or len(reflections) < min_support:
            return patterns

        # Analyze commitment themes and reflection themes
        commitment_themes = defaultdict(list)
        reflection_themes = defaultdict(list)

        for commitment in commitments:
            content = commitment.get("content", "").lower()
            # Simple theme extraction (keywords)
            if "improve" in content:
                commitment_themes["improvement"].append(commitment["id"])
            elif "learn" in content:
                commitment_themes["learning"].append(commitment["id"])
            elif "communicate" in content:
                commitment_themes["communication"].append(commitment["id"])

        for reflection in reflections:
            content = reflection.get("content", "").lower()
            if "improve" in content or "better" in content:
                reflection_themes["improvement"].append(reflection["id"])
            elif "learn" in content or "understand" in content:
                reflection_themes["learning"].append(reflection["id"])
            elif "communicate" in content or "talk" in content:
                reflection_themes["communication"].append(reflection["id"])

        # Find theme correlations
        for theme, commitment_ids in commitment_themes.items():
            if theme in reflection_themes and len(commitment_ids) >= min_support:
                reflection_ids = reflection_themes[theme]

                # Calculate correlation strength
                confidence = min(
                    1.0, (len(commitment_ids) + len(reflection_ids)) / 20.0
                )

                # Generate evidence tokens
                evidence_tokens = []
                for cid in commitment_ids[:5] + reflection_ids[:5]:
                    try:
                        digest = self.memegraph.event_digest(cid)
                        evidence_tokens.append(f"[{cid}:{digest[:8]}]")
                    except Exception:
                        continue

                hypothesis = (
                    f"If I make commitments about '{theme}' then I reflect on '{theme}' "
                    f"outcomes within 10 events measured by theme_consistency"
                )

                pattern = PatternCandidate(
                    pattern_type="outcome_correlation",
                    description=(
                        f"Commitment-reflection correlation for '{theme}': "
                        f"{len(commitment_ids)} commitments, {len(reflection_ids)} reflections"
                    ),
                    confidence=confidence,
                    evidence_tokens=evidence_tokens,
                    suggested_hypothesis=hypothesis,
                    supporting_events=commitment_ids + reflection_ids,
                )

                patterns.append(pattern)

        return patterns

    def generate_hypothesis_from_pattern(
        self, pattern: PatternCandidate, hypothesis_tracker: HypothesisTracker
    ) -> str | None:
        """
        Convert a pattern candidate into a formal hypothesis.

        Args:
            pattern: Pattern candidate to convert
            hypothesis_tracker: Tracker to validate and create hypothesis

        Returns:
            Hypothesis ID if created successfully, None otherwise
        """
        # Use the suggested hypothesis from the pattern
        hypothesis = hypothesis_tracker.create_hypothesis(
            statement=pattern.suggested_hypothesis,
            priors=pattern.confidence,
            evidence_tokens=pattern.evidence_tokens,
        )

        return hypothesis.id if hypothesis else None

    def get_synthesis_summary(self, snapshot: SynthesisSnapshot) -> str:
        """
        Generate human-readable summary of synthesis results.

        Args:
            snapshot: Synthesis snapshot to summarize

        Returns:
            Summary string for logging or display
        """
        summary_lines = [
            f"Synthesis Analysis - {snapshot.timestamp}",
            f"Analyzed {snapshot.inputs['event_count']} recent events",
            (
                f"Discovered {len(snapshot.patterns)} patterns across "
                f"{len(snapshot.inputs.get('pattern_types', []))} types"
            ),
            "",
        ]

        for i, pattern in enumerate(snapshot.patterns[:3], 1):
            summary_lines.append(
                f"{i}. {pattern.pattern_type}: {pattern.description} (confidence: {pattern.confidence:.2f})"
            )

        if len(snapshot.patterns) > 3:
            summary_lines.append(f"... and {len(snapshot.patterns) - 3} more patterns")

        summary_lines.extend(
            ["", f"Top hypothesis candidates: {len(snapshot.candidates)}", ""]
        )

        for i, candidate in enumerate(snapshot.candidates[:2], 1):
            summary_lines.append(f"{i}. {candidate}")

        return "\n".join(summary_lines)
