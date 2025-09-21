#!/usr/bin/env python3
"""
Test script to verify reflection system fixes.
This tests the reflection quality improvements and policy loop prevention.
"""

import sys
import os

# Add the pmm directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pmm"))

from pmm.runtime.reflector import accept


def test_empty_reflection_rejection():
    """Test that empty reflections are properly rejected."""
    events = []
    text = ""
    accepted, reason, meta = accept(text, events, 0)
    assert not accepted
    assert reason == "too_short" or reason == "empty_reflection"
    print("✓ Empty reflection rejection test passed")


def test_repetitive_reflection_rejection():
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
    print(f"Debug repetitive: accepted={accepted}, reason={reason}, meta={meta}")
    assert not accepted
    # The policy keywords in the base text might trigger policy_loop_detected instead
    assert reason in ["too_repetitive", "ngram_duplicate", "policy_loop_detected"]
    print("✓ Repetitive reflection rejection test passed")


def test_policy_loop_detection():
    """Test that policy adjustment loops are detected."""
    events = []

    # Test with policy-heavy content that has low quality (short, repetitive policy words)
    # This should trigger policy_loop_detected because it has >2 policy keywords and low quality
    text = "Policy: lower novelty_threshold decrease increase\n."  # Low quality, many policy keywords
    accepted, reason, meta = accept(text, events, 0)
    print(f"Debug policy: accepted={accepted}, reason={reason}, meta={meta}")
    assert not accepted
    assert reason == "policy_loop_detected"
    print("✓ Policy loop detection test passed")


def test_good_reflection_acceptance():
    """Test that good quality reflections are accepted."""
    events = []
    text = "I notice my IAS is 0.85 and GAS is 0.67.\nMy recent commitments show good progress and I should focus on trait development."
    accepted, reason, meta = accept(text, events, 0)
    print(f"Debug good: accepted={accepted}, reason={reason}, meta={meta}")
    assert accepted
    # Can be accepted via normal path or bootstrap (both are valid)
    assert reason in ["ok", "bootstrap_accept"]
    print("✓ Good reflection acceptance test passed")


def test_forced_reflection_quality():
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
    print(
        f"Debug forced content: accepted={accepted}, reason={reason}, content_len={len(content)}"
    )
    assert accepted
    assert "quality_score" in meta
    print("✓ Forced reflection quality test passed")


if __name__ == "__main__":
    print("Testing reflection system fixes...")

    test_empty_reflection_rejection()
    test_repetitive_reflection_rejection()
    test_policy_loop_detection()
    test_good_reflection_acceptance()
    test_forced_reflection_quality()

    print("\nAll reflection system tests passed! ✓")
    print("\nSummary of fixes:")
    print("- Added quality checks to prevent empty reflections")
    print("- Added repetitive content detection")
    print("- Added policy loop detection to prevent pathological adjustments")
    print("- Enhanced stage advancement to require reflection quality")
    print("- Improved reflection acceptance logic with stricter thresholds")
