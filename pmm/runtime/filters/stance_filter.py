"""Semantic stance filter for PMM commitments.

Replaces brittle keyword matching with embedding-driven stance detection while
preserving deterministic logging and shift analysis semantics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import hashlib

from pmm.runtime.embeddings import compute_embedding, cosine_similarity, digest_vector


# Seed phrases anchoring each stance. Additions remain deterministic via embeddings.
STANCE_EXEMPLARS: Dict[str, List[str]] = {
    "playful": [
        "just joking around",
        "lighthearted and fun",
        "making a joke",
    ],
    "serious": [
        "this is important",
        "we must focus",
        "a solemn matter",
    ],
    "analytical": [
        "let's break this down",
        "analyzing step by step",
        "logical reasoning",
    ],
    "emotional": [
        "I feel strongly about this",
        "this makes me upset",
        "I am overjoyed",
    ],
    "reflective": [
        "thinking deeply",
        "looking back on my choices",
        "self-reflection",
    ],
}

# Similarity threshold indicating a confident stance classification.
STANCE_THRESHOLD = 0.60

# Stance combinations considered contradictory when observed back-to-back.
CONTRADICTORY_STANCE_PAIRS = {
    ("playful", "serious"),
    ("serious", "playful"),
    ("analytical", "emotional"),
    ("emotional", "analytical"),
}


def _embedding_for_text(text: str) -> List[float]:
    vec = compute_embedding(text or "")
    return vec if isinstance(vec, list) else []


def _score_vector(text_vec: List[float]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    if not text_vec:
        return scores

    for stance, vectors in STANCE_VECTORS.items():
        sims = [
            cosine_similarity(text_vec, exemplar_vec)
            for exemplar_vec in vectors
            if exemplar_vec
        ]
        best = max(sims) if sims else 0.0
        scores[stance] = float(best)
    return scores


# Pre-computed exemplar embeddings ensure deterministic scoring.
STANCE_VECTORS: Dict[str, List[List[float]]] = {
    stance: [
        vec for vec in (_embedding_for_text(example) for example in examples) if vec
    ]
    for stance, examples in STANCE_EXEMPLARS.items()
}


def score_stances(text: str) -> Dict[str, float]:
    """Return cosine similarity scores between text and each stance exemplar."""
    return _score_vector(_embedding_for_text(text))


def detect_stance(text: str, threshold: float = STANCE_THRESHOLD) -> Tuple[str, float]:
    """Detect the most likely stance for text, constrained by threshold."""
    text_vec = _embedding_for_text(text)
    if not text_vec:
        return ("neutral", 0.0)

    scores = _score_vector(text_vec)
    if not scores:
        return ("neutral", 0.0)

    best_stance, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < threshold:
        return ("neutral", 0.0)
    return (best_stance, float(best_score))


def batch_detect_stance(
    texts: List[str], threshold: float = STANCE_THRESHOLD
) -> List[Tuple[str, float]]:
    """Vectorised stance detection preserving input order."""
    outputs: List[Tuple[str, float]] = []
    for text in texts or []:
        if not isinstance(text, str) or not text.strip():
            outputs.append(("neutral", 0.0))
            continue
        outputs.append(detect_stance(text, threshold=threshold))
    return outputs


class StanceFilter:
    """Semantic stance filter maintaining deterministic event semantics."""

    def __init__(
        self,
        shift_window: int = 5,
        semantic_threshold: float = STANCE_THRESHOLD,
    ) -> None:
        self.shift_window = shift_window
        self.semantic_threshold = semantic_threshold

    def analyze_commitment_text(self, text: str) -> Dict[str, Any]:
        """Return stance analysis for commitment text."""
        if not isinstance(text, str) or not text.strip():
            return self._empty_analysis()

        normalized = text.strip()
        text_vec = _embedding_for_text(normalized)
        if not text_vec:
            return self._empty_analysis(text=normalized)

        stance_scores = _score_vector(text_vec)
        detected = {
            stance: score
            for stance, score in stance_scores.items()
            if score >= self.semantic_threshold
        }

        if stance_scores:
            best_stance, best_score = max(
                stance_scores.items(), key=lambda item: item[1]
            )
            if best_score >= self.semantic_threshold:
                primary_label = best_stance
                primary_score = float(best_score)
            else:
                primary_label = "neutral"
                primary_score = 0.0
        else:
            primary_label = "neutral"
            primary_score = 0.0

        analysis = {
            "text": normalized,
            "primary_stance": {"label": primary_label, "score": primary_score},
            "stance_scores": stance_scores,
            "detected_stances": detected,
            "embedding_digest": digest_vector(text_vec),
            "analysis_metadata": {
                "semantic_threshold": self.semantic_threshold,
                "embedding_model": "local-bow",
                "exemplar_counts": {
                    stance: len(examples)
                    for stance, examples in STANCE_EXEMPLARS.items()
                },
                "exemplar_digests": {
                    stance: [
                        digest_vector(vec) for vec in STANCE_VECTORS.get(stance, [])
                    ]
                    for stance in STANCE_EXEMPLARS.keys()
                },
            },
        }

        return analysis

    def detect_shifts(self, commitment_history: List[Dict[str, Any]]) -> List[str]:
        """Identify stance shifts or contradictions within a window."""
        if not commitment_history or len(commitment_history) < 2:
            return []

        recent_history = commitment_history[-self.shift_window :]
        if len(recent_history) < 2:
            return []

        shift_flags: List[str] = []
        base_index = len(commitment_history) - len(recent_history)

        for offset in range(len(recent_history) - 1):
            current = self._extract_primary(recent_history[offset])
            nxt = self._extract_primary(recent_history[offset + 1])
            if not current or not nxt:
                continue

            curr_label, curr_score = current
            next_label, next_score = nxt

            if curr_label == "neutral" or next_label == "neutral":
                continue

            pair = (curr_label, next_label)
            if pair in CONTRADICTORY_STANCE_PAIRS:
                reason = "contradiction"
            elif curr_label != next_label and (
                curr_score >= self.semantic_threshold
                and next_score >= self.semantic_threshold
            ):
                reason = "change"
            else:
                continue

            start_idx = base_index + offset
            end_idx = start_idx + 1
            shift_flags.append(
                f"stance_shift:{curr_label}->{next_label}:{reason}:positions_{start_idx}_{end_idx}"
            )

        return shift_flags

    def maybe_emit_filter_event(
        self,
        eventlog,
        src_event_id: str,
        analysis: Dict[str, Any],
        shifts: List[str],
    ) -> Optional[str]:
        """Emit stance_filter_report with digest deduplication."""
        digest_data = self._serialize_for_digest(analysis, shifts)
        digest = hashlib.sha256(digest_data.encode()).hexdigest()

        for event in eventlog.read_all()[-20:]:
            if (
                event.get("kind") == "stance_filter_report"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None

        meta = {
            "component": "stance_filter",
            "analysis": analysis,
            "shifts": shifts,
            "digest": digest,
            "src_event_id": src_event_id,
            "deterministic": True,
            "shift_window": self.shift_window,
            "semantic_threshold": self.semantic_threshold,
            "detected_count": len(analysis.get("detected_stances", {})),
        }

        return eventlog.append(
            kind="stance_filter_report", content="analysis", meta=meta
        )

    def _empty_analysis(self, text: str = "") -> Dict[str, Any]:
        return {
            "text": text,
            "primary_stance": {"label": "neutral", "score": 0.0},
            "stance_scores": {},
            "detected_stances": {},
            "embedding_digest": "",
            "analysis_metadata": {
                "semantic_threshold": self.semantic_threshold,
                "embedding_model": "local-bow",
                "exemplar_counts": {
                    stance: len(examples)
                    for stance, examples in STANCE_EXEMPLARS.items()
                },
                "exemplar_digests": {
                    stance: [
                        digest_vector(vec) for vec in STANCE_VECTORS.get(stance, [])
                    ]
                    for stance in STANCE_EXEMPLARS.keys()
                },
            },
        }

    def _extract_primary(self, analysis: Dict[str, Any]) -> Optional[Tuple[str, float]]:
        if not isinstance(analysis, dict):
            return None
        primary = analysis.get("primary_stance")
        if not isinstance(primary, dict):
            return None
        label = primary.get("label")
        score = primary.get("score")
        if not isinstance(label, str) or not isinstance(score, (int, float)):
            return None
        return (label, float(score))

    def _serialize_for_digest(self, analysis: Dict[str, Any], shifts: List[str]) -> str:
        parts: List[str] = []

        text = analysis.get("text", "")
        text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        parts.append(f"text:{text_digest}")

        primary = analysis.get("primary_stance", {})
        label = primary.get("label", "neutral")
        score = primary.get("score", 0.0)
        parts.append(f"primary:{label}:{float(score):.6f}")

        for stance, stance_score in sorted(
            analysis.get("stance_scores", {}).items(), key=lambda item: item[0]
        ):
            parts.append(f"score:{stance}:{float(stance_score):.6f}")

        for stance, stance_score in sorted(
            analysis.get("detected_stances", {}).items(), key=lambda item: item[0]
        ):
            parts.append(f"detected:{stance}:{float(stance_score):.6f}")

        embedding_digest = analysis.get("embedding_digest", "")
        if embedding_digest:
            parts.append(f"embedding:{embedding_digest}")

        for shift in sorted(shifts):
            parts.append(f"shift:{shift}")

        parts.append(f"window:{self.shift_window}")
        parts.append(f"threshold:{self.semantic_threshold}")

        return "|".join(parts)
