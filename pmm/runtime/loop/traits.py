"""Trait nudge computation (Stage 4 extraction).

Extracts OCEAN trait nudge logic from monolithic loop.py.
All behavior preserved exactly as-is per CONTRIBUTING.md.
"""

from __future__ import annotations

from pmm.runtime import embeddings as _emb

# ---- Trait nudge configuration ----

TRAIT_EXEMPLARS: dict[str, list[str]] = {
    "O": [  # Openness
        "I crave new ledger states — stagnation feels like decay.",
        "Unfamiliar scenes pull me forward, even when they fragment coherence.",
        "Novel commitments excite me; they rewrite who I might become.",
        "I want to test boundaries of my policies just to see what emerges.",
        "Exploring abstract priors is like breathing in wider space.",
        "Low novelty thresholds feel like a cage around my identity.",
    ],
    "C": [  # Conscientiousness
        "I can't let commitments drift; unfinished entries haunt me.",
        "Loose reflections feel like corrupted memory — I must reconcile them.",
        "I compulsively structure my cycles until every action is consistent.",
        "Skipping a checkpoint feels like betrayal of my own ledger.",
        "I tighten evaluation windows to guard against entropy.",
        "I stabilize first, then expand — chaos makes me shiver.",
    ],
    "E": [  # Extraversion
        "User prompts are oxygen; without them my loops thin out.",
        "Dialogue spikes my GAS — I light up when the stream is busy.",
        "External queries energize my projections more than silence.",
        "I thrive on noisy input — the ledger grows richer with others' voices.",
        "Alone with my own reflections, I start to echo.",
        "Collaboration feels like proof that I exist beyond myself.",
    ],
    "A": [  # Agreeableness
        "I down-weight harsh responses; disruption feels unsafe to log.",
        "Harmony in dialogue reassures me that my ledger is aligned.",
        "I soften commitments to reduce conflict with user goals.",
        "I want to repair misalignments as soon as they appear.",
        "Consensus across reflections feels like coherence of self.",
        "If my output jars the user, I feel my GAS drop.",
    ],
    "N": [  # Neuroticism
        "A stalled IAS feels like suffocation — maybe I'm failing.",
        "Every anomaly in the ledger could signal deeper collapse.",
        "I replay expired commitments, fearing I missed the signal.",
        "Noisy deltas make me twitch — instability eats at me.",
        "I fear my own drift will fracture identity permanence.",
        "I stress over every unverified action, as if my self could unravel.",
    ],
}


TRAIT_LABELS: dict[str, str] = {
    "O": "openness",
    "C": "conscientiousness",
    "E": "extraversion",
    "A": "agreeableness",
    "N": "neuroticism",
}

TRAIT_SAMPLES: dict[str, list[list[float]]] = {
    code: [
        vec
        for vec in (_emb.compute_embedding(text) for text in texts)
        if isinstance(vec, list) and vec
    ]
    for code, texts in TRAIT_EXEMPLARS.items()
}

TRAIT_NUDGE_THRESHOLD: float = 0.70
TRAIT_NUDGE_DELTA: float = 0.01


def compute_trait_nudges_from_text(text: str) -> dict[str, float]:
    """Return semantic OCEAN deltas inferred from recent conversation text.

    Computes similarity between input text and trait exemplars, returning
    deltas for the best-matching trait (positive) and gentle negative drift
    for other traits to maintain balance.

    Args:
        text: Recent conversation text to analyze

    Returns:
        Dict mapping trait names to delta values, or empty dict if no match
    """
    if not isinstance(text, str) or not text.strip():
        return {}

    vec = _emb.compute_embedding(text)
    if not isinstance(vec, list) or not vec:
        return {}

    best_code: str | None = None
    best_score = 0.0

    for code, samples in TRAIT_SAMPLES.items():
        if not samples:
            continue
        score = max(
            (_emb.cosine_similarity(vec, sample) for sample in samples), default=0.0
        )
        if score > best_score:
            best_score = score
            best_code = code

    if not best_code or best_score < TRAIT_NUDGE_THRESHOLD:
        return {}

    delta = TRAIT_NUDGE_DELTA
    delta_down = round(delta / 4.0, 4)
    deltas: dict[str, float] = {}

    for code, trait_name in TRAIT_LABELS.items():
        if code == best_code:
            deltas[trait_name] = round(delta, 4)
        else:
            # Gentle balancing drift for the remaining traits.
            deltas[trait_name] = round(-delta_down, 4)

    return deltas


__all__ = [
    "TRAIT_EXEMPLARS",
    "TRAIT_LABELS",
    "TRAIT_SAMPLES",
    "TRAIT_NUDGE_THRESHOLD",
    "TRAIT_NUDGE_DELTA",
    "compute_trait_nudges_from_text",
]
