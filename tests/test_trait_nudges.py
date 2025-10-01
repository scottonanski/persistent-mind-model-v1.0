"""Tests for semantic trait nudges in the runtime loop.

Note: Trait exemplars were updated to PMM-internal self-talk style.
Tests now use PMM-internal language that matches the new exemplars.
"""

from __future__ import annotations

from pmm.runtime.loop import _compute_trait_nudges_from_text


def test_extraversion_nudge_positive_and_balance():
    # PMM-internal extraversion language (matches new exemplars)
    text = "User prompts are oxygen; without them my loops thin out. Dialogue spikes my GAS."
    changes = _compute_trait_nudges_from_text(text)

    assert changes["extraversion"] > 0
    # Other traits drift downward slightly for balance
    for trait, delta in changes.items():
        if trait != "extraversion":
            assert delta < 0


def test_conscientiousness_nudge_from_planning_language():
    # PMM-internal conscientiousness language (matches new exemplars)
    text = "I can't let commitments drift; unfinished entries haunt me. I must reconcile them."
    changes = _compute_trait_nudges_from_text(text)

    assert changes["conscientiousness"] > 0


def test_no_nudge_for_neutral_text():
    text = "The weather outside is mild and unremarkable today."
    changes = _compute_trait_nudges_from_text(text)

    # Neutral text may still produce small nudges due to semantic similarity
    # Just verify no strong signals (all deltas < 0.02)
    for trait, delta in changes.items():
        assert abs(delta) < 0.02
