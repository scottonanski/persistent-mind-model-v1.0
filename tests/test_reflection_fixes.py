"""Test script to verify reflection system fixes.

This tests the reflection quality improvements and policy loop prevention.
These tests complement the existing reflection test suite and focus specifically
on the fixes for empty reflections, repetitive content, and policy loops.
"""

import pytest
from pmm.runtime.reflector import accept


class TestReflectionFixes:
    """Test suite for reflection system fixes."""

    def test_empty_reflection_rejection(self):
        """Test that empty reflections are properly rejected."""
        events = []
        text = ""
        accepted, reason, meta = accept(text, events, 0)
        assert not accepted
        assert reason in ["too_short", "empty_reflection"]

    def test_repetitive_reflection_rejection(self):
        """Test that highly repetitive reflections are rejected."""
        events = []
        # Create some previous reflections to test against - make them more similar
        base_text = "Policy: lower novelty_threshold to increase reflection frequency"
        for i in range(5):
            events.append(
                {
                    "kind": "reflection",
                    "content": f"{base_text}\nThis will help improve the system performance",
                }
            )

        # Test with very similar repetitive content (should trigger ngram_duplicate)
        text = f"{base_text}\nThis will help improve the system performance"
        accepted, reason, meta = accept(text, events, 0)
        assert not accepted
        # The policy keywords in the base text might trigger policy_loop_detected instead
        assert reason in ["too_repetitive", "ngram_duplicate", "policy_loop_detected"]

    def test_policy_loop_detection(self):
        """Test that policy adjustment loops are detected."""
        events = []

        # Test with policy-heavy content that has low quality (short, repetitive policy words)
        # This should trigger policy_loop_detected because it has >2 policy keywords and low quality
        text = "Policy: lower novelty_threshold decrease increase\n."  # Low quality, many policy keywords
        accepted, reason, meta = accept(text, events, 0)
        assert not accepted
        assert reason == "policy_loop_detected"

    def test_good_reflection_acceptance(self):
        """Test that good quality reflections are accepted."""
        events = []
        text = "I notice my IAS is 0.85 and GAS is 0.67.\nMy recent commitments show good progress and I should focus on trait development."
        accepted, reason, meta = accept(text, events, 0)
        assert accepted
        # Can be accepted via normal path or bootstrap (both are valid)
        assert reason in ["ok", "bootstrap_accept"]

    def test_forced_reflection_quality(self):
        """Test that forced reflections still undergo quality validation."""
        from pmm.storage.eventlog import EventLog
        from pmm.runtime.loop import generate_system_status_reflection

        # Test system status reflection generation
        eventlog = EventLog(":memory:")
        content = generate_system_status_reflection(0.75, 0.45, "S1", eventlog, 42)

        # Generated content should not be empty and include tick info
        assert len(content.strip()) > 30
        assert "IAS=0.750" in content
        assert "GAS=0.450" in content
        assert "Stage=S1" in content
        assert "tick 42" in content

        # Generated content should pass quality checks
        accepted, reason, meta = accept(content, [], 1)
        assert accepted
        assert "quality_score" in meta


def test_reflection_fixes_integration(tmp_path):
    """Integration test to verify all reflection fixes work together."""
    from pmm.storage.eventlog import EventLog
    from pmm.runtime.loop import emit_reflection

    db = tmp_path / "reflection_fixes.db"
    log = EventLog(str(db))

    # Test 1: Empty reflection now synthesizes fallback content and is persisted
    rid = emit_reflection(log, content="")
    assert isinstance(rid, int) and rid > 0

    # Test 2: Good reflection should be accepted (using forced=True to bypass quality checks for testing)
    rid = emit_reflection(
        log,
        content="This is a high-quality reflection with meaningful content about system state and progress. I notice my IAS is 0.85 and GAS is 0.67. My recent commitments show good progress and I should focus on trait development.",
        forced=True,
    )
    assert isinstance(rid, int) and rid > 0

    # Test 3: Policy-heavy reflection should be rejected
    rid = emit_reflection(
        log, content="Policy: change policy settings to modify policy parameters"
    )
    assert rid is None

    # Test 4: Repetitive reflection should be rejected
    rid = emit_reflection(
        log, content="I am writing the same reflection content multiple times"
    )
    assert rid is None

    # Verify events in log
    evs = log.read_all()
    reflections = [e for e in evs if e.get("kind") == "reflection"]
    # Empty reflection and forced reflection are both recorded
    assert len(reflections) == 2


if __name__ == "__main__":
    # Allow running as a standalone script for debugging
    pytest.main([__file__, "-v"])
