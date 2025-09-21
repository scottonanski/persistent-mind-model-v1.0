"""Tests for semantic trait nudges in the runtime loop."""

from __future__ import annotations

from pmm.runtime.loop import _compute_trait_nudges_from_text


def test_extraversion_nudge_positive_and_balance():
    text = "I'm excited to share this update with everyone and connect more."
    changes = _compute_trait_nudges_from_text(text)

    assert changes["extraversion"] > 0
    # Other traits drift downward slightly for balance
    for trait, delta in changes.items():
        if trait != "extraversion":
            assert delta < 0


def test_conscientiousness_nudge_from_planning_language():
    text = "I will stay organized and carefully plan each step to follow through."
    changes = _compute_trait_nudges_from_text(text)

    assert changes["conscientiousness"] > 0


def test_no_nudge_for_neutral_text():
    text = "The weather outside is mild and unremarkable today."
    changes = _compute_trait_nudges_from_text(text)

    assert changes == {}
