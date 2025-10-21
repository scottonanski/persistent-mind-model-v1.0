"""Semantic commitment extraction using embedding-based intent detection."""

from __future__ import annotations

import logging
from typing import Any

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


COMMITMENT_EXEMPLARS: dict[str, list[str]] = {
    "open": [
        "I will complete this task",
        "I plan to work on this",
        "I am committing to this action",
        "My goal is to accomplish this",
        "I will adjust the threshold to 0.45",
        "I will set openness to 0.52",
        "I will increase the parameter",
        "I will update the policy",
        "I will use the name Ada",
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

# Negative exemplars: what analysis/reflection looks like (to reject)
ANALYSIS_EXEMPLARS: list[str] = [
    "This action leverages the threshold",
    "This action leverages the threshold to improve alignment",
    "The system indicates growth potential",
    "Aligns with our growth mechanics",
    "Expected IAS is approximately 0.35",
    "The metrics suggest improvement",
    "This approach indicates alignment",
    "The data shows progression",
    "Analysis reveals opportunities",
    "The proposed action would leverage the threshold",
    "Such a step utilizes mechanisms for alignment",
    "The model processes events based on ledger state",
    "When we start a new session the system will query",
    "I'll use this approach to analyze future inputs",
    "The LLM will generate responses by consulting",
    "On the next turn I plan to check the metrics",
]

# Pre-compute analysis samples
ANALYSIS_SAMPLES: list[dict[str, Any]] = []

STRUCTURAL_EXEMPLARS: dict[str, list[str]] = {
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


INTENT_STRUCTURE_REQUIREMENTS: dict[str, dict[str, float]] = {
    "open": {"first_person": 0.45, "future_focus": 0.45},
    "close": {"completion": 0.45},
    "expire": {"abandonment": 0.45},
}


def _embedding(text: str) -> list[float]:
    vec = compute_embedding(text or "")
    return vec if isinstance(vec, list) else []


def _prepare_samples(
    exemplars: dict[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    samples: dict[str, list[dict[str, Any]]] = {}
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

# Prepare analysis samples
for text in ANALYSIS_EXEMPLARS:
    vec = _embedding(text)
    if vec:
        ANALYSIS_SAMPLES.append({"text": text, "vector": vec})


def _max_similarity(
    vec: list[float], samples: list[dict[str, Any]]
) -> tuple[float, str]:
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


def _best_intent(vec: list[float]) -> tuple[str, float, str]:
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


def _structural_scores(vec: list[float]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for key, samples in STRUCTURAL_SAMPLES.items():
        score, _ = _max_similarity(vec, samples)
        scores[key] = score
    return scores


def detect_commitment(
    text: str, threshold: float = COMMITMENT_THRESHOLD
) -> dict[str, Any]:
    """Detect semantic commitment intent for the given text via embeddings.

    Uses dual exemplar matching: high commitment score AND low analysis score.
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

    # Dual matching: check against analysis exemplars (negative signal)
    analysis_score = 0.0
    if vec and ANALYSIS_SAMPLES:
        analysis_score, _ = _max_similarity(vec, ANALYSIS_SAMPLES)

    # Comparative rejection: reject if analysis similarity is stronger or nearly as strong
    # as commitment similarity. This treats detection as a binary classifier (commitment vs. analysis)
    # and prevents false positives where analytical statements share vocabulary with commitments.
    # Primary check: strict margin (0.05) for "open" intents where false positives are most common.
    # Secondary check: if analysis_score is very high (>0.75) for any intent, likely pure analysis.
    if (intent == "open" and analysis_score >= score - 0.05) or analysis_score > 0.75:
        return {
            "intent": "none",
            "score": 0.0,
            "threshold": threshold,
            "exemplar": "",
            "structure": structures,
            "embedding_digest": digest,
        }

    required = INTENT_STRUCTURE_REQUIREMENTS.get(intent, {})
    structure_terms = [structures.get(name, 0.0) for name in required.keys()]
    structure_avg = (
        sum(structure_terms) / len(structure_terms) if structure_terms else 0.0
    )
    # Use structural signal as a deterministic boost instead of a hard gate.
    structure_boost = 0.9 + 0.25 * max(0.0, structure_avg - 0.5)
    structure_boost = min(1.1, max(0.9, structure_boost))
    adjusted_score = min(1.0, score * structure_boost)

    # Apply analysis penalty: reduce score proportionally for high analysis similarity
    # This catches residual cases where comparative rejection isn't sufficient
    # Only apply to "open" intents where false positives are problematic
    # Penalty starts at analysis_score > 0.55, capped at 40% reduction
    if intent == "open" and analysis_score > 0.55:
        analysis_penalty = min(
            0.40, (analysis_score - 0.55) * 0.89
        )  # ~0.40 at analysis=1.0
        adjusted_score = max(0.0, adjusted_score * (1.0 - analysis_penalty))

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
    texts: list[str], threshold: float = COMMITMENT_THRESHOLD
) -> list[tuple[str, str, float]]:
    """Return ``(text, intent, score)`` for all detected commitments in ``texts``."""
    results: list[tuple[str, str, float]] = []
    for text in texts or []:
        analysis = detect_commitment(text, threshold=threshold)
        if analysis["intent"] != "none":
            results.append((text, analysis["intent"], analysis["score"]))
    return results


class CommitmentExtractor:
    """Embedding-backed commitment intent detector."""

    def __init__(self, eventlog: EventLog | None = None) -> None:
        self.eventlog = eventlog
        self.commit_thresh = COMMITMENT_THRESHOLD

    def detect_intent(self, text: str) -> dict[str, Any]:
        """Analyze text and return semantic commitment metadata."""
        return detect_commitment(text, threshold=self.commit_thresh)

    def score(self, text: str) -> float:
        """Return the semantic commitment score for ``text``."""
        analysis = self.detect_intent(text)
        return float(analysis["score"])

    def extract_best_sentence(self, text: str) -> str | None:
        """Return the highest scoring commitment sentence from the input text.

        Uses a paragraph-aware approach that:
        1. Splits text into lines or sentences depending on structure
        2. Filters out short headings (< 20 chars or ending with ':')
        3. Evaluates each segment for commitment intent
        4. Returns the segment with the highest commitment score
        """
        if not isinstance(text, str) or not text.strip():
            return None

        # Determine if text has multi-line structure or is a single line
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]

        # If text has multiple lines, use line-based splitting (paragraph-aware)
        # Otherwise, split on periods for single-line text
        if len(lines) > 1:
            segments = lines
        else:
            # Single line: split on periods but preserve context
            segments = [seg.strip() for seg in text.split(".")]
            segments = [seg for seg in segments if seg]

        # Filter out likely headings: very short segments or segments ending with ':'
        # Headings are typically < 20 chars and often end with colons
        candidates = []
        for segment in segments:
            # Skip markdown headers
            if segment.startswith("#") or segment.startswith("**"):
                continue
            if segment.startswith("-") or segment.startswith("*"):
                # Keep bullet points but strip the marker
                segment = segment.lstrip("-*").strip()
            if segment and segment[0].isdigit() and "." in segment[:3]:
                # Strip numbered list markers like "1. "
                segment = (
                    segment.split(".", 1)[1].strip() if "." in segment else segment
                )

            # Skip very short segments or segments that are just headings
            if len(segment) < 20 or segment.endswith(":"):
                continue

            candidates.append(segment)

        if not candidates:
            return None

        best_sentence: str | None = None
        best_analysis: dict[str, Any] | None = None

        for candidate in candidates:
            analysis = self.detect_intent(candidate)
            if analysis["intent"] == "none":
                continue
            if best_analysis is None or analysis["score"] > best_analysis["score"]:
                best_sentence = candidate
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

    def _vector(self, text: str) -> list[float]:
        """Expose the deterministic embedding used for semantic detection."""
        return _embedding(text)
