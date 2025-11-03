"""Tests for Phase 3 hypothesis tracker."""

import os
import tempfile

import pytest

from pmm.runtime.hypothesis_tracker import (
    HypothesisStatus,
    HypothesisTracker,
)
from pmm.storage.eventlog import EventLog


class TestHypothesisTracker:
    """Test hypothesis lifecycle management."""

    @pytest.fixture
    def eventlog(self):
        """Create temporary eventlog for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            eventlog = EventLog(db_path)
            # Add some test events for evidence
            for i in range(5):
                eventlog.append(
                    kind="test_event",
                    content=f"Test event {i}",
                    meta={"test_data": f"value_{i}"},
                )
            yield eventlog
        finally:
            os.unlink(db_path)

    @pytest.fixture
    def tracker(self, eventlog):
        """Create hypothesis tracker with test eventlog."""
        return HypothesisTracker(eventlog)

    def test_parse_hypothesis_statement_valid(self, tracker):
        """Test parsing valid hypothesis statements."""
        statement = "If users ask questions then I provide detailed answers within 5 events measured by response_quality"

        result = tracker.parse_hypothesis_statement(statement)

        assert result is not None
        condition, prediction, window, metric = result
        assert condition == "users ask questions"
        assert prediction == "I provide detailed answers"
        assert window == "5 events"
        assert metric == "response_quality"

    def test_parse_hypothesis_statement_invalid(self, tracker):
        """Test parsing invalid hypothesis statements."""
        invalid_statements = [
            "Invalid statement format",
            "If condition then prediction",  # Missing window/metric
            "condition then prediction within window measured by metric",  # Missing If
            "If condition then prediction within window",  # Missing measured by
        ]

        for statement in invalid_statements:
            result = tracker.parse_hypothesis_statement(statement)
            assert result is None

    def test_validate_evidence_tokens_valid(self, tracker):
        """Test validation of properly formatted evidence tokens."""
        # Use tokens with correct lowercase hex format (8+ chars)
        valid_tokens = ["[1:acf76915]", "[2:3696e906]", "[3:1cc39255]"]

        result = tracker.validate_evidence_tokens(valid_tokens)

        # Should return tokens that reference existing events
        assert len(result) == 3  # All should be valid
        for token in result:
            assert token.startswith("[")
            assert token.endswith("]")
            # Verify format: [ID:lowercase_hex]
            parts = token[1:-1].split(":")
            assert len(parts) == 2
            assert parts[0].isdigit()
            assert parts[1].islower()  # Should be lowercase hex
            assert len(parts[1]) >= 8  # Should be at least 8 chars

    def test_validate_evidence_tokens_invalid(self, tracker):
        """Test rejection of malformed evidence tokens."""
        invalid_tokens = [
            "not_a_token",
            "[1]",  # Missing digest
            "[abcd1234]",  # Missing ID
            "[1:short]",  # Digest too short
            "[1:ABCD1234]",  # Uppercase not allowed
        ]

        result = tracker.validate_evidence_tokens(invalid_tokens)
        assert len(result) == 0  # All should be invalid

    def test_create_hypothesis_valid(self, tracker):
        """Test creating a valid hypothesis."""
        statement = "If users ask questions then I provide detailed answers within 5 events measured by response_quality"
        evidence_tokens = ["[1:acf76915]"]  # Use valid lowercase hex format

        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.7, evidence_tokens=evidence_tokens
        )

        assert hypothesis is not None
        assert hypothesis.statement == statement
        assert hypothesis.priors == 0.7
        assert hypothesis.status == HypothesisStatus.ACTIVE
        assert hypothesis.posterior == 0.7  # Should start at priors
        assert len(hypothesis.evidence_tokens) == 1
        assert hypothesis.id in tracker._active_hypotheses

    def test_create_hypothesis_invalid_statement(self, tracker):
        """Test rejecting hypothesis with invalid statement."""
        invalid_statement = "This is not a valid hypothesis format"

        hypothesis = tracker.create_hypothesis(
            statement=invalid_statement,
            priors=0.5,
            evidence_tokens=["[1:acf76915]"],  # Use valid format
        )

        assert hypothesis is None

    def test_create_hypothesis_invalid_priors(self, tracker):
        """Test rejecting hypothesis with invalid priors."""
        statement = "If condition then prediction within 5 events measured by metric"

        # Invalid priors values
        for priors in [-0.1, 1.5, 2.0]:
            hypothesis = tracker.create_hypothesis(
                statement=statement,
                priors=priors,
                evidence_tokens=["[1:acf76915]"],  # Use valid format
            )
            assert hypothesis is None

    def test_create_hypothesis_no_evidence(self, tracker):
        """Test rejecting hypothesis without evidence tokens."""
        statement = "If condition then prediction within 5 events measured by metric"

        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.5, evidence_tokens=[]
        )

        assert hypothesis is None

    def test_create_hypothesis_concurrent_limit(self, tracker):
        """Test respecting concurrent hypothesis limit."""
        statement = "If condition then prediction within 5 events measured by metric"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        # Create hypotheses up to the limit
        hypotheses = []
        for i in range(tracker._max_concurrent):
            hypothesis = tracker.create_hypothesis(
                statement=f"{statement} {i}",
                priors=0.5,
                evidence_tokens=evidence_tokens,
            )
            if hypothesis:
                hypotheses.append(hypothesis)

        assert len(hypotheses) == tracker._max_concurrent

        # Try to create one more - should fail
        extra_hypothesis = tracker.create_hypothesis(
            statement=f"{statement} extra", priors=0.5, evidence_tokens=evidence_tokens
        )

        assert extra_hypothesis is None

    def test_add_evidence_supporting(self, tracker):
        """Test adding supporting evidence to hypothesis."""
        statement = "If users ask questions then I provide detailed answers within 5 events measured by response_quality"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.5, evidence_tokens=evidence_tokens
        )

        assert hypothesis is not None
        initial_posterior = hypothesis.posterior

        # Add supporting evidence
        success = tracker.add_evidence(
            hypothesis_id=hypothesis.id, outcome=True, metric_value=0.8  # Supporting
        )

        assert success is True
        updated_hypothesis = tracker.get_hypothesis(hypothesis.id)
        assert updated_hypothesis.supporting_evidence == 1
        assert updated_hypothesis.posterior > initial_posterior  # Should increase
        assert updated_hypothesis.confidence > 0.0  # Should increase from initial 0.5

    def test_add_evidence_contradicting(self, tracker):
        """Test adding contradicting evidence to hypothesis."""
        statement = "If users ask questions then I provide detailed answers within 5 events measured by response_quality"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.5, evidence_tokens=evidence_tokens
        )

        assert hypothesis is not None
        initial_posterior = hypothesis.posterior

        # Add contradicting evidence
        success = tracker.add_evidence(
            hypothesis_id=hypothesis.id,
            outcome=False,  # Contradicting
            metric_value=0.2,
        )

        assert success is True
        updated_hypothesis = tracker.get_hypothesis(hypothesis.id)
        assert updated_hypothesis.contradicting_evidence == 1
        assert updated_hypothesis.posterior < initial_posterior  # Should decrease

    def test_status_transition_to_supported(self, tracker):
        """Test hypothesis status transition to supported."""
        statement = "If users ask questions then I provide detailed answers within 5 events measured by response_quality"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.5, evidence_tokens=evidence_tokens
        )

        # Add enough supporting evidence to trigger status change
        for i in range(15):  # Need more evidence to reach posterior ≥0.8
            tracker.add_evidence(
                hypothesis_id=hypothesis.id, outcome=True, metric_value=0.8
            )

        updated_hypothesis = tracker.get_hypothesis(hypothesis.id)
        assert updated_hypothesis.status == HypothesisStatus.SUPPORTED
        assert updated_hypothesis.confidence >= tracker._min_confidence_threshold
        assert updated_hypothesis.posterior >= 0.8

    def test_status_transition_to_rejected(self, tracker):
        """Test hypothesis status transition to rejected."""
        statement = "If users ask questions then I provide detailed answers within 5 events measured by response_quality"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.5, evidence_tokens=evidence_tokens
        )

        # Add enough contradicting evidence to trigger rejection
        for i in range(15):  # Need more evidence to reach posterior ≤0.2
            tracker.add_evidence(
                hypothesis_id=hypothesis.id, outcome=False, metric_value=0.2
            )

        updated_hypothesis = tracker.get_hypothesis(hypothesis.id)
        assert updated_hypothesis.status == HypothesisStatus.REJECTED
        assert updated_hypothesis.confidence >= tracker._min_confidence_threshold
        assert updated_hypothesis.posterior <= 0.2

    def test_get_active_hypotheses(self, tracker):
        """Test retrieving active hypotheses."""
        statement = "If condition then prediction within 5 events measured by metric"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        # Create multiple hypotheses
        hypotheses = []
        for i in range(3):
            hypothesis = tracker.create_hypothesis(
                statement=f"{statement} {i}",
                priors=0.5,
                evidence_tokens=evidence_tokens,
            )
            if hypothesis:
                hypotheses.append(hypothesis)

        active_hypotheses = tracker.get_active_hypotheses()
        assert len(active_hypotheses) == 3

        # Add evidence to transition one to supported
        tracker.add_evidence(hypotheses[0].id, True, 0.8)
        for _ in range(7):
            tracker.add_evidence(hypotheses[0].id, True, 0.8)

        active_hypotheses = tracker.get_active_hypotheses()
        assert len(active_hypotheses) == 2  # One should have transitioned to supported

    def test_get_supported_hypotheses(self, tracker):
        """Test retrieving supported hypotheses."""
        statement = "If condition then prediction within 5 events measured by metric"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.5, evidence_tokens=evidence_tokens
        )

        # Initially no supported hypotheses
        supported = tracker.get_supported_hypotheses()
        assert len(supported) == 0

        # Add enough evidence to make it supported
        for _ in range(15):  # Need more evidence to reach posterior ≥0.8
            tracker.add_evidence(hypothesis.id, True, 0.8)

        supported = tracker.get_supported_hypotheses()
        assert len(supported) == 1
        assert supported[0].id == hypothesis.id
        assert supported[0].status == HypothesisStatus.SUPPORTED

    def test_close_hypothesis(self, tracker):
        """Test closing hypothesis."""
        statement = "If condition then prediction within 5 events measured by metric"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.5, evidence_tokens=evidence_tokens
        )

        assert hypothesis.id in tracker._active_hypotheses

        success = tracker.close_hypothesis(hypothesis.id)

        assert success is True
        assert hypothesis.id not in tracker._active_hypotheses

        # Should not be able to close again
        success = tracker.close_hypothesis(hypothesis.id)
        assert success is False

    def test_cleanup_expired_hypotheses(self, tracker):
        """Test cleanup of old inactive hypotheses."""
        statement = "If condition then prediction within 5 events measured by metric"
        evidence_tokens = ["[1:acf76915]"]  # Use valid format

        # Create and close a hypothesis
        hypothesis = tracker.create_hypothesis(
            statement=statement, priors=0.5, evidence_tokens=evidence_tokens
        )

        # Add evidence to make it inactive (supported)
        for _ in range(15):  # Need more evidence to reach posterior ≥0.8
            tracker.add_evidence(hypothesis.id, True, 0.8)

        # Manually set old timestamp for testing
        old_hypothesis = tracker._active_hypotheses[hypothesis.id]
        old_hypothesis.updated_at = "2023-01-01T00:00:00Z"

        # Run cleanup (should remove old inactive hypotheses)
        cleaned = tracker.cleanup_expired_hypotheses(max_age_hours=1)

        assert cleaned >= 0  # Should clean up the old hypothesis
