"""Regression tests for commitment extraction from multi-paragraph reflections."""

from __future__ import annotations

from pmm.commitments.extractor import CommitmentExtractor


def test_extract_best_sentence_prefers_action_over_heading() -> None:
    """Regression test for event 1503: ensure headings don't override actionable sentences.

    The reflection contained detailed analysis with section headings like "Policy Constraints:"
    that were being extracted as commitments instead of the actual actionable sentences.
    This test ensures extract_best_sentence() prefers sentences with executable intent.
    """
    extractor = CommitmentExtractor()

    # Simplified version of event 1503 reflection structure
    reflection = """
**Analytical Reflection**

Current Stage & Commitments:
- I am in Stage S4, where both IAS = 0.940 and GAS = 1.000 satisfy required thresholds.
- All key traits are within acceptable ranges.

Policy Constraints:
- Cooldown Novelty Threshold = 0.55: This policy limits how aggressively new traits can be introduced.

Proposed Intervention:
- I propose incrementally raising my Conscientiousness trait by 0.05 points (targeting C=0.45).

Implementation:
- Action: Set traits.C = traits.C + 0.05 in the ledger, recording this change as Event ID.
- Why-mechanics: This adjustment directly improves my trait profile without breaching policy limits.

Next Steps:
1. Execute the ledger update for Conscientiousness.
2. Monitor IAS and verify that no new events exceed the novelty threshold.
"""

    best = extractor.extract_best_sentence(reflection)

    # Should extract an actionable sentence, not a heading
    assert best is not None
    assert "Policy Constraints:" not in best
    assert "Current Stage & Commitments:" not in best
    assert "Next Steps:" not in best

    # Should contain actionable content
    # The extractor should find one of the actual commitment sentences
    actionable_phrases = [
        "propose incrementally raising",
        "Set traits.C",
        "Execute the ledger update",
    ]
    assert any(
        phrase in best for phrase in actionable_phrases
    ), f"Expected actionable content, got: {best}"


def test_extract_best_sentence_handles_multiline_with_headings() -> None:
    """Ensure extract_best_sentence works with text containing multiple headings."""
    extractor = CommitmentExtractor()

    text = """
Analysis:
The current metrics show room for improvement.

Action Plan:
I will increase the threshold parameter to 0.65.

Expected Outcome:
This should improve alignment scores.
"""

    best = extractor.extract_best_sentence(text)

    assert best is not None
    assert "I will increase the threshold parameter to 0" in best
    assert "Analysis:" not in best
    assert "Action Plan:" not in best


def test_extract_best_sentence_rejects_pure_headings() -> None:
    """Verify that text with only headings and no actionable content returns None."""
    extractor = CommitmentExtractor()

    text = """
Policy Constraints:
Current Stage & Commitments:
Next Steps:
"""

    best = extractor.extract_best_sentence(text)

    # Should return None since there's no actionable content
    assert best is None
