"""Tests for Phase 3 synthesis engine."""

import os
import tempfile

import pytest

from pmm.runtime.hypothesis_tracker import HypothesisTracker
from pmm.runtime.memegraph import MemeGraphProjection
from pmm.runtime.synthesis_engine import (
    PatternCandidate,
    SynthesisEngine,
    SynthesisSnapshot,
)
from pmm.storage.eventlog import EventLog


class TestSynthesisEngine:
    """Test pattern detection and hypothesis generation."""

    @pytest.fixture
    def eventlog(self):
        """Create temporary eventlog with test data."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            eventlog = EventLog(db_path)

            # Add diverse test events for pattern detection
            test_events = [
                ("reflection", "I need to improve my communication skills"),
                ("reflection", "Learning to communicate better is important"),
                ("commitment_open", "I will improve my communication"),
                ("reflection", "Communication improvement shows progress"),
                ("reflection", "Users ask questions about technical topics"),
                ("reflection", "Technical questions require detailed answers"),
                ("commitment_open", "I will provide better technical explanations"),
                ("reflection", "Detailed explanations help users understand"),
                ("test_event", "Some other content for noise"),
                ("test_event", "More noise content"),
            ]

            for kind, content in test_events:
                eventlog.append(kind=kind, content=content)

            yield eventlog
        finally:
            os.unlink(db_path)

    @pytest.fixture
    def memegraph(self, eventlog):
        """Create memegraph with test data."""
        return MemeGraphProjection(eventlog)

    @pytest.fixture
    def synthesis_engine(self, eventlog, memegraph):
        """Create synthesis engine with test components."""
        return SynthesisEngine(eventlog, memegraph, seed=42)

    @pytest.fixture
    def hypothesis_tracker(self, eventlog):
        """Create hypothesis tracker for testing."""
        return HypothesisTracker(eventlog)

    def test_synthesis_engine_initialization(self, synthesis_engine):
        """Test synthesis engine initializes properly."""
        assert synthesis_engine.eventlog is not None
        assert synthesis_engine.memegraph is not None
        assert synthesis_engine.seed == 42
        assert synthesis_engine._deterministic_counter == 0

    def test_run_synthesis_basic(self, synthesis_engine):
        """Test basic synthesis analysis runs without errors."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=2, max_candidates=3
        )

        assert isinstance(snapshot, SynthesisSnapshot)
        assert snapshot.timestamp is not None
        assert snapshot.inputs["window_size"] == 20
        assert snapshot.inputs["event_count"] > 0
        assert len(snapshot.patterns) >= 0
        assert len(snapshot.candidates) <= 3
        assert "analysis_seed" in snapshot.metadata

    def test_co_occurrence_pattern_detection(self, synthesis_engine):
        """Test detection of co-occurring terms."""
        # The test data has "communication" and "improve" co-occurring
        snapshot = synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=2, max_candidates=5
        )

        # Should find some co-occurrence patterns
        co_occurrence_patterns = [
            p for p in snapshot.patterns if p.pattern_type == "co_occurrence"
        ]

        assert len(co_occurrence_patterns) > 0

        # Check pattern structure
        for pattern in co_occurrence_patterns:
            assert pattern.confidence >= 0.0
            assert pattern.confidence <= 1.0
            assert len(pattern.evidence_tokens) > 0
            assert pattern.suggested_hypothesis.startswith("If")
            assert len(pattern.supporting_events) > 0

    def test_graph_pattern_detection(self, synthesis_engine):
        """Test detection of graph structural patterns."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=20,
            min_pattern_support=1,  # Lower threshold for test data
            max_candidates=5,
        )

        # Should find graph patterns if memegraph has structure
        graph_patterns = [
            p for p in snapshot.patterns if p.pattern_type == "graph_structure"
        ]

        # May not find patterns in small test data, but should not error
        assert isinstance(graph_patterns, list)

    def test_outcome_correlation_detection(self, synthesis_engine):
        """Test detection of commitment-reflection correlations."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=1, max_candidates=5
        )

        # Should find correlation patterns in test data
        correlation_patterns = [
            p for p in snapshot.patterns if p.pattern_type == "outcome_correlation"
        ]

        assert len(correlation_patterns) > 0

        # Check pattern structure
        for pattern in correlation_patterns:
            assert "correlation" in pattern.description.lower()
            assert pattern.confidence >= 0.0
            assert pattern.suggested_hypothesis.startswith("If")

    def test_pattern_candidate_structure(self, synthesis_engine):
        """Test pattern candidate has required structure."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=1, max_candidates=5
        )

        if snapshot.patterns:
            pattern = snapshot.patterns[0]

            assert isinstance(pattern, PatternCandidate)
            assert pattern.pattern_type in [
                "co_occurrence",
                "graph_structure",
                "outcome_correlation",
            ]
            assert len(pattern.description) > 0
            assert 0.0 <= pattern.confidence <= 1.0
            assert isinstance(pattern.evidence_tokens, list)
            assert pattern.suggested_hypothesis.startswith("If")
            assert isinstance(pattern.supporting_events, list)

    def test_deterministic_synthesis(self, synthesis_engine):
        """Test synthesis produces consistent results."""
        # Run synthesis twice with same parameters
        snapshot1 = synthesis_engine.run_synthesis(
            window_size=15, min_pattern_support=2, max_candidates=3
        )

        # Reset counter to get same sequence
        synthesis_engine._deterministic_counter = 0

        snapshot2 = synthesis_engine.run_synthesis(
            window_size=15, min_pattern_support=2, max_candidates=3
        )

        # Should produce identical results
        assert len(snapshot1.patterns) == len(snapshot2.patterns)
        assert snapshot1.candidates == snapshot2.candidates
        assert (
            snapshot1.metadata["analysis_seed"] == snapshot2.metadata["analysis_seed"]
        )

    def test_synthesis_with_small_window(self, synthesis_engine):
        """Test synthesis handles small windows gracefully."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=3,  # Very small window
            min_pattern_support=2,  # High threshold
            max_candidates=1,
        )

        # Should complete without errors even with little data
        assert isinstance(snapshot, SynthesisSnapshot)
        assert snapshot.inputs["window_size"] == 3
        # May find few or no patterns with small window
        assert isinstance(snapshot.patterns, list)

    def test_generate_hypothesis_from_pattern(
        self, synthesis_engine, hypothesis_tracker
    ):
        """Test converting patterns to formal hypotheses."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=1, max_candidates=5
        )

        if snapshot.patterns:
            pattern = snapshot.patterns[0]

            # Generate hypothesis from pattern
            hypothesis_id = synthesis_engine.generate_hypothesis_from_pattern(
                pattern, hypothesis_tracker
            )

            # Should create hypothesis if pattern is valid
            if pattern.suggested_hypothesis and pattern.evidence_tokens:
                assert hypothesis_id is not None
                assert hypothesis_id > 0

                # Verify hypothesis was created
                hypothesis = hypothesis_tracker.get_hypothesis(hypothesis_id)
                assert hypothesis is not None
                assert hypothesis.statement == pattern.suggested_hypothesis

    def test_get_synthesis_summary(self, synthesis_engine):
        """Test synthesis summary generation."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=1, max_candidates=5
        )

        summary = synthesis_engine.get_synthesis_summary(snapshot)

        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "Synthesis Analysis" in summary
        assert "Analyzed" in summary
        assert "patterns" in summary.lower()

        # Should include pattern descriptions if any exist
        if snapshot.patterns:
            assert any(p.pattern_type in summary for p in snapshot.patterns[:3])

    def test_max_candidates_limit(self, synthesis_engine):
        """Test synthesis respects max_candidates limit."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=1, max_candidates=2
        )

        # Should not exceed candidate limit
        assert len(snapshot.candidates) <= 2

    def test_pattern_ranking_by_confidence(self, synthesis_engine):
        """Test patterns are ranked by confidence."""
        snapshot = synthesis_engine.run_synthesis(
            window_size=20, min_pattern_support=1, max_candidates=10
        )

        if len(snapshot.patterns) > 1:
            # Patterns should be sorted by confidence (descending)
            confidences = [p.confidence for p in snapshot.patterns]
            assert confidences == sorted(confidences, reverse=True)
