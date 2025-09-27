from __future__ import annotations

import re
from typing import Dict

COMPOSITE_THRESHOLD = 0.6

_CITATION_PATTERN = re.compile(r"e(\d+)")

_ACTION_TOKENS = {
    "action",
    "step",
    "plan",
    "commit",
    "close",
    "schedule",
    "execute",
    "test",
    "implement",
}

_FALSIFIABLE_TOKENS = {
    "test",
    "measure",
    "verify",
    "evidence",
    "experiment",
    "check",
}

_NOVELTY_TOKENS = {
    "new",
    "novel",
    "insight",
    "emerg",
    "unexpected",
    "potential",
    "discovery",
}


def score_insight(text: str) -> Dict[str, float]:
    """Crude heuristic scorer for assistant insights."""
    if not text or not text.strip():
        return {
            "novelty": 0.0,
            "specificity": 0.0,
            "actionability": 0.0,
            "falsifiability": 0.0,
            "composite": 0.0,
            "citations": 0,
            "passes": False,
        }

    lower = text.lower()

    citations = len(set(_CITATION_PATTERN.findall(lower)))
    specificity = min(1.0, citations * 0.3)

    actionability = 0.2
    if any(tok in lower for tok in _ACTION_TOKENS):
        actionability = 0.6
    if "next" in lower and "step" in lower:
        actionability = 0.7

    falsifiability = 0.2
    if any(tok in lower for tok in _FALSIFIABLE_TOKENS):
        falsifiability = 0.6
    if "what would show" in lower or "if this fails" in lower:
        falsifiability = 0.7

    novelty = 0.3
    if any(tok in lower for tok in _NOVELTY_TOKENS):
        novelty = 0.6
    if "because" in lower or "so that" in lower:
        novelty = min(1.0, novelty + 0.1)

    composite = (novelty + specificity + actionability + falsifiability) / 4.0
    result = {
        "novelty": round(novelty, 3),
        "specificity": round(specificity, 3),
        "actionability": round(actionability, 3),
        "falsifiability": round(falsifiability, 3),
        "composite": round(composite, 3),
        "citations": citations,
        "passes": composite >= COMPOSITE_THRESHOLD,
    }
    return result
