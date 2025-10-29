"""Semantic intent detection for commitment claims.

Uses deterministic embeddings (no external providers) against versioned
exemplars to classify sentences as 'open' (pledge), 'adjectival' (descriptive),
'closed' (completed), or 'none'.
"""

from __future__ import annotations

from pmm.commitments.exemplars import COMMITMENT_EXEMPLARS
from pmm.runtime.embeddings import compute_embedding, cosine_similarity


def _split_into_sentences(text: str) -> list[str]:
    """Deterministic sentence splitter (no regex).

    Splits on '.', '!', '?' when followed by whitespace or end-of-string.
    Collapses empty fragments.
    """
    if not text:
        return []
    out: list[str] = []
    current: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        current.append(ch)
        if ch in ".!?":
            # Look ahead
            j = i + 1
            if j >= n or text[j] in " \n\r\t":
                frag = "".join(current).strip()
                if frag:
                    out.append(frag)
                current = []
        i += 1
    if current:
        frag = "".join(current).strip()
        if frag:
            out.append(frag)
    return out


def detect_commitment_intent(
    sentence: str, threshold: float = 0.60
) -> tuple[str, float]:
    """Classify sentence intent using semantic similarity to exemplars.

    Returns: (intent, confidence) where intent ∈ {"open","adjectival","closed","none"}
    """
    if not sentence or not sentence.strip():
        return ("none", 0.0)
    emb_s = compute_embedding(sentence)
    best_intent = "none"
    best_score = 0.0
    for intent, exemplars in COMMITMENT_EXEMPLARS.items():
        for ex in exemplars:
            emb_e = compute_embedding(ex)
            score = cosine_similarity(emb_s, emb_e)
            if score > best_score:
                best_score = score
                best_intent = intent
    if best_score >= float(threshold):
        return best_intent, float(best_score)
    return ("none", float(best_score))


def extract_commitment_claims(
    text: str, *, threshold: float = 0.70
) -> list[tuple[str, str, float]]:
    """Extract commitment sentences using semantic intent detection.

    Returns a list of (sentence, intent, confidence) for 'open' intents only.
    """
    claims: list[tuple[str, str, float]] = []
    for s in _split_into_sentences(text or ""):
        # Skip questions; not pledges
        if s.strip().endswith("?"):
            continue
        intent, conf = detect_commitment_intent(s, threshold=threshold)
        if intent == "open":
            claims.append((s, intent, conf))
    return claims
