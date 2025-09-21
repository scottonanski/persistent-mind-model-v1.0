"""Semantic commitment extraction using embedding-based intent detection."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from pmm.runtime.embeddings import compute_embedding, cosine_similarity, digest_vector

try:  # pragma: no cover - optional dependency during tests
    from pmm.storage.eventlog import EventLog
except ImportError:  # pragma: no cover - fallback for typing only usage
    EventLog = None  # type: ignore

try:  # pragma: no cover - config is optional during tests
    from pmm.config import COMMITMENT_THRESHOLD as CONFIG_COMMITMENT_THRESHOLD
except ImportError:  # pragma: no cover - default when config absent
    CONFIG_COMMITMENT_THRESHOLD = None


logger = logging.getLogger(__name__)

DEFAULT_COMMITMENT_THRESHOLD = 0.62

COMMITMENT_THRESHOLD = (
    float(CONFIG_COMMITMENT_THRESHOLD)
    if CONFIG_COMMITMENT_THRESHOLD is not None
    else DEFAULT_COMMITMENT_THRESHOLD
)


COMMITMENT_EXEMPLARS: Dict[str, List[str]] = {
    "open": [
        "I will complete this task",
        "I plan to work on this",
        "I am committing to this action",
        "My goal is to accomplish this",
    ],
    "close": [
        "I have completed this task",
        "This commitment is done",
        "I finished my goal",
        "I am closing this commitment",
    ],
    "expire": [
        "I can no longer do this",
        "This goal is no longer relevant",
        "I am abandoning this task",
    ],
}


STRUCTURAL_EXEMPLARS: Dict[str, List[str]] = {
    "first_person": [
        "I will",
        "we will",
        "this is my commitment",
    ],
    "future_focus": [
        "I will take action soon",
        "we are going to work on this",
        "my next step is to do this",
    ],
    "completion": [
        "I have completed this",
        "this task is done",
        "we finished our goal",
    ],
    "abandonment": [
        "I can no longer do this",
        "this goal is no longer relevant",
        "we are abandoning this task",
    ],
}


INTENT_STRUCTURE_REQUIREMENTS: Dict[str, Dict[str, float]] = {
    "open": {"first_person": 0.45, "future_focus": 0.45},
    "close": {"completion": 0.45},
    "expire": {"abandonment": 0.45},
}


def _embedding(text: str) -> List[float]:
    vec = compute_embedding(text or "")
    return vec if isinstance(vec, list) else []


def _prepare_samples(
    exemplars: Dict[str, List[str]],
) -> Dict[str, List[Dict[str, Any]]]:
    samples: Dict[str, List[Dict[str, Any]]] = {}
    for label, texts in exemplars.items():
        vectors = []
        for text in texts:
            vec = _embedding(text)
            if vec:
                vectors.append({"text": text, "vector": vec})
        samples[label] = vectors
    return samples


COMMITMENT_SAMPLES = _prepare_samples(COMMITMENT_EXEMPLARS)
STRUCTURAL_SAMPLES = _prepare_samples(STRUCTURAL_EXEMPLARS)


def _max_similarity(
    vec: List[float], samples: List[Dict[str, Any]]
) -> Tuple[float, str]:
    if not vec or not samples:
        return 0.0, ""
    best_score = 0.0
    best_text = ""
    for sample in samples:
        score = float(cosine_similarity(vec, sample["vector"]))
        if score > best_score:
            best_score = score
            best_text = sample["text"]
    return best_score, best_text


def _best_intent(vec: List[float]) -> Tuple[str, float, str]:
    best_intent = "none"
    best_score = 0.0
    best_exemplar = ""
    for intent, samples in COMMITMENT_SAMPLES.items():
        score, exemplar = _max_similarity(vec, samples)
        if score > best_score:
            best_intent = intent
            best_score = score
            best_exemplar = exemplar
    return best_intent, best_score, best_exemplar


def _structural_scores(vec: List[float]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for key, samples in STRUCTURAL_SAMPLES.items():
        score, _ = _max_similarity(vec, samples)
        scores[key] = score
    return scores


def detect_commitment(
    text: str, threshold: float = COMMITMENT_THRESHOLD
) -> Dict[str, Any]:
    """Detect semantic commitment intent for the given text via embeddings.

    Structural exemplars act as a soft boost rather than a hard requirement.
    """
    if not isinstance(text, str) or not text.strip():
        return {
            "intent": "none",
            "score": 0.0,
            "threshold": threshold,
            "exemplar": "",
            "structure": {},
            "embedding_digest": "",
        }

    cleaned = text.strip()
    vec = _embedding(cleaned)
    digest = digest_vector(vec) if vec else ""
    intent, score, exemplar = _best_intent(vec)
    structures = _structural_scores(vec)

    required = INTENT_STRUCTURE_REQUIREMENTS.get(intent, {})
    structure_terms = [structures.get(name, 0.0) for name in required.keys()]
    structure_avg = (
        sum(structure_terms) / len(structure_terms) if structure_terms else 0.0
    )
    # Use structural signal as a deterministic boost instead of a hard gate.
    structure_boost = 0.9 + 0.25 * max(0.0, structure_avg - 0.5)
    structure_boost = min(1.1, max(0.9, structure_boost))
    adjusted_score = min(1.0, score * structure_boost)

    if adjusted_score < threshold:
        return {
            "intent": "none",
            "score": 0.0,
            "threshold": threshold,
            "exemplar": "",
            "structure": structures,
            "embedding_digest": digest,
        }

    return {
        "intent": intent,
        "score": adjusted_score,
        "threshold": threshold,
        "exemplar": exemplar,
        "structure": structures,
        "embedding_digest": digest,
    }


def extract_commitments(
    texts: List[str], threshold: float = COMMITMENT_THRESHOLD
) -> List[Tuple[str, str, float]]:
    """Return ``(text, intent, score)`` for all detected commitments in ``texts``."""
    results: List[Tuple[str, str, float]] = []
    for text in texts or []:
        analysis = detect_commitment(text, threshold=threshold)
        if analysis["intent"] != "none":
            results.append((text, analysis["intent"], analysis["score"]))
    return results


class CommitmentExtractor:
    """Embedding-backed commitment intent detector."""

    def __init__(self, eventlog: Optional["EventLog"] = None) -> None:
        self.eventlog = eventlog
        self.commit_thresh = COMMITMENT_THRESHOLD

    def detect_intent(self, text: str) -> Dict[str, Any]:
        """Analyze text and return semantic commitment metadata."""
        return detect_commitment(text, threshold=self.commit_thresh)

    def score(self, text: str) -> float:
        """Return the semantic commitment score for ``text``."""
        analysis = self.detect_intent(text)
        return float(analysis["score"])

    def extract_best_sentence(self, text: str) -> Optional[str]:
        """Return the highest scoring commitment sentence from the input text."""
        if not isinstance(text, str) or not text.strip():
            return None

        sentences = [segment.strip() for segment in text.replace("\n", " ").split(".")]
        sentences = [s for s in sentences if s]

        best_sentence: Optional[str] = None
        best_analysis: Optional[Dict[str, Any]] = None

        for sentence in sentences:
            analysis = self.detect_intent(sentence)
            if analysis["intent"] == "none":
                continue
            if best_analysis is None or analysis["score"] > best_analysis["score"]:
                best_sentence = sentence
                best_analysis = analysis

        if self.eventlog is not None:
            meta = {
                "extracted_sentence": best_sentence or "",
                "intent": best_analysis["intent"] if best_analysis else "none",
                "score": best_analysis["score"] if best_analysis else 0.0,
                "threshold": self.commit_thresh,
                "exemplar": best_analysis["exemplar"] if best_analysis else "",
                "structure": best_analysis["structure"] if best_analysis else {},
                "embedding_digest": (
                    best_analysis["embedding_digest"] if best_analysis else ""
                ),
            }
            try:
                self.eventlog.append(
                    kind="commitment_extraction", content=text, meta=meta
                )
            except Exception:  # pragma: no cover - defensive logging only
                logger.exception("Failed to append commitment extraction event")

        return best_sentence

    def _vector(self, text: str) -> List[float]:
        """Expose the deterministic embedding used for semantic detection."""
        return _embedding(text)
