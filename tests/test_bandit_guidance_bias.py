from __future__ import annotations

from typing import Dict

import pmm.runtime.reflection_bandit as rb


def _baseline_from_means(means: Dict[str, float]) -> str:
    # Pick argmax deterministically in ARMS order
    best = None
    best_v = -1.0
    for arm in rb.ARMS:
        v = float(means.get(arm, 0.0))
        if v > best_v:
            best = arm
            best_v = v
    return best or rb.ARMS[0]


def test_no_guidance_matches_baseline_and_zero_deltas():
    means = {
        "succinct": 0.2,
        "question_form": 0.1,
        "narrative": 0.1,
        "checklist": 0.0,
        "analytical": 0.0,
    }
    base = _baseline_from_means(means)
    arm, delta = rb.choose_arm_biased(means, guidance_items=[])
    assert arm == base
    assert set(delta.keys()) == set(rb.ARMS)
    assert all(abs(v) < 1e-9 for v in delta.values())


def test_within_margin_can_flip_but_clear_winner_cannot():
    # Close competition between succinct and question_form
    means = {
        "succinct": 0.20,
        "question_form": 0.19,
        "narrative": 0.00,
        "checklist": 0.00,
        "analytical": 0.00,
    }
    # Push question type strongly; delta capped at EPS_BIAS
    items = [{"type": "question", "score": 10.0}]
    arm, delta = rb.choose_arm_biased(means, guidance_items=items)
    assert arm == "question_form"  # flipped within margin
    assert abs(delta["question_form"]) <= rb.EPS_BIAS

    # Clear winner scenario: analytical ahead by large margin
    means2 = {
        "succinct": 0.00,
        "question_form": 0.00,
        "narrative": 0.00,
        "checklist": 0.00,
        "analytical": 0.50,
    }
    items2 = [{"type": "checklist", "score": 10.0}]
    arm2, delta2 = rb.choose_arm_biased(means2, guidance_items=items2)
    assert arm2 == "analytical"  # cannot flip a clear winner
    assert abs(delta2["checklist"]) <= rb.EPS_BIAS
