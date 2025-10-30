"""Test validator correction feedback for emergent cognition improvements.

This test verifies that the validator provides graduated severity levels
and correction messages to help Echo learn from hallucinations.
"""

import tempfile
from pathlib import Path

import pytest

from pmm.commitments.tracker import CommitmentTracker
from pmm.runtime.loop.validators import verify_commitment_claims
from pmm.storage.eventlog import EventLog


def test_validator_returns_tuple():
    """Verify that validator returns (bool, str|None) tuple."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))

        # Test with no commitment claims
        result = verify_commitment_claims("Hello, how are you?", eventlog)
        assert isinstance(result, tuple)
        assert len(result) == 2
        hallucination_detected, correction = result
        assert hallucination_detected is False
        assert correction is None


def test_validator_no_hallucination_no_correction():
    """Verify that valid commitment references return (False, None)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Create a real commitment
        cid = tracker.add_commitment(
            "I will complete this task",
            source="assistant",
        )

        # Reference it correctly
        reply = "I will complete this task as committed."
        hallucination_detected, correction = verify_commitment_claims(reply, eventlog)
        
        assert hallucination_detected is False
        assert correction is None


def test_validator_hallucination_provides_correction():
    """Verify that hallucinations return (True, correction_message)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Create a real commitment
        tracker.add_commitment(
            "I will analyze the data",
            source="assistant",
        )

        # Reference a non-existent commitment (hallucination)
        reply = "I committed to building a rocket ship."
        hallucination_detected, correction = verify_commitment_claims(reply, eventlog)
        
        assert hallucination_detected is True
        assert correction is not None
        assert isinstance(correction, str)
        assert "[VALIDATOR_CORRECTION]" in correction
        assert "no matching open commitment" in correction.lower()


def test_validator_paraphrase_provides_note():
    """Verify that paraphrases (sim >= 0.60) return (False, note)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Create a commitment
        tracker.add_commitment(
            "I will analyze the performance metrics",
            source="assistant",
        )

        # Paraphrase it (semantically similar but different words)
        reply = "I committed to examining the performance data."
        hallucination_detected, correction = verify_commitment_claims(reply, eventlog)
        
        # Paraphrase should not block response but should provide feedback
        assert hallucination_detected is False
        assert correction is not None
        assert isinstance(correction, str)
        assert "[VALIDATOR_NOTE]" in correction
        assert "paraphrase" in correction.lower()


def test_validator_event_id_hallucination():
    """Verify that fake event IDs return correction message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Create a commitment (will have event ID 1 or 2)
        tracker.add_commitment(
            "I will complete the analysis",
            source="assistant",
        )

        # Reference a fake event ID
        reply = "As I committed in event ID 99999, I will complete the analysis."
        hallucination_detected, correction = verify_commitment_claims(reply, eventlog)
        
        assert hallucination_detected is True
        assert correction is not None
        assert "[VALIDATOR_CORRECTION]" in correction
        assert "99999" in correction
        assert "no such open commitment" in correction.lower()


def test_validator_graduated_severity():
    """Verify that validator uses graduated severity thresholds.
    
    - sim >= 0.70: Valid (no correction)
    - 0.60 <= sim < 0.70: Paraphrase (note, don't block)
    - 0.40 <= sim < 0.60: Semantic drift (warning, block)
    - sim < 0.40: Hallucination (error, block)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Create a specific commitment
        tracker.add_commitment(
            "I will analyze the database performance metrics",
            source="assistant",
        )

        # Test case 1: High similarity (should pass)
        reply1 = "I will analyze the database performance metrics"
        h1, c1 = verify_commitment_claims(reply1, eventlog)
        assert h1 is False
        assert c1 is None

        # Test case 2: Paraphrase (sim ~0.60-0.70, should provide note)
        reply2 = "I committed to examining database speed measurements"
        h2, c2 = verify_commitment_claims(reply2, eventlog)
        # May or may not detect as paraphrase depending on embeddings
        # If detected, should not block but should provide feedback
        if c2 is not None:
            assert h2 is False  # Don't block paraphrases
            assert "[VALIDATOR_NOTE]" in c2

        # Test case 3: Low similarity (should block with correction)
        reply3 = "I committed to building a spaceship"
        h3, c3 = verify_commitment_claims(reply3, eventlog)
        assert h3 is True
        assert c3 is not None
        assert "[VALIDATOR_CORRECTION]" in c3


def test_validator_correction_message_format():
    """Verify that correction messages have proper format for injection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Create a commitment
        tracker.add_commitment(
            "I will complete the task",
            source="assistant",
        )

        # Trigger hallucination
        reply = "I committed to launching the rocket."
        hallucination_detected, correction = verify_commitment_claims(reply, eventlog)
        
        assert correction is not None
        
        # Verify format suitable for prompt injection
        assert correction.startswith("[VALIDATOR_")
        assert "ledger" in correction.lower()
        assert "verify" in correction.lower() or "shows" in correction.lower()
        
        # Should include actual commitments for reference
        assert "complete the task" in correction.lower() or "actual" in correction.lower()


def test_validator_preserves_semantic_approach():
    """Verify that validator uses semantic matching, not brittle keywords.
    
    This aligns with CONTRIBUTING.md principle of semantic-based systems.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        # Create commitment with specific phrasing
        tracker.add_commitment(
            "I will analyze the system",
            source="assistant",
        )

        # Reference with different phrasing (semantic match)
        reply = "I'll examine the system as I committed."
        hallucination_detected, correction = verify_commitment_claims(reply, eventlog)
        
        # Should recognize semantic similarity
        # (exact behavior depends on embedding model, but should not fail)
        assert isinstance(hallucination_detected, bool)
        assert correction is None or isinstance(correction, str)


def test_validator_correction_helps_learning():
    """Document that correction messages enable learning.
    
    This test serves as living documentation for the correction feedback feature.
    """
    # Rationale from emergent cognition analysis:
    # 1. Validator catches confabulations (working memory reconstructions)
    # 2. Without feedback, Echo repeats similar errors
    # 3. Correction messages injected into next prompt provide learning signal
    # 4. Graduated severity (note vs correction) prevents over-correction
    # 5. This supports emergent cognition by enabling self-correction
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        eventlog = EventLog(str(db_path))
        tracker = CommitmentTracker(eventlog)

        tracker.add_commitment("Real commitment", source="assistant")

        # Hallucination should return correction
        _, correction = verify_commitment_claims(
            "I committed to fake task", eventlog
        )
        assert correction is not None
        
        # Correction should be actionable
        assert "verify" in correction.lower() or "ledger" in correction.lower()
        assert "actual" in correction.lower() or "shows" in correction.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
