"""Semantic commitment prioritization using embedding-based urgency detection."""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from pmm.runtime.embeddings import compute_embedding, cosine_similarity, digest_vector

try:  # pragma: no cover - optional during tests
    from pmm.storage.eventlog import EventLog
except ImportError:  # pragma: no cover - typing fallback
    EventLog = None  # type: ignore


logger = logging.getLogger(__name__)

URGENCY_THRESHOLD = 0.70

URGENCY_EXEMPLARS: dict[str, list[str]] = {
    "high": [
        "this must be done immediately",
        "urgent priority",
        "as soon as possible",
        "this cannot wait",
        "we need to push this out right away",
        "this has to happen right now",
    ],
    "medium": [
        "should be done soon",
        "important but not urgent",
        "in the next few days",
        "I will handle this shortly",
    ],
    "low": [
        "whenever I get around to it",
        "not urgent",
        "this can wait",
        "optional task",
    ],
}

URGENCY_WEIGHTS: dict[str, float] = {"high": 1.0, "medium": 0.6, "low": 0.2}

W1_URGENCY = 0.6
W2_NOVELTY = 0.3
W3_AGE_PENALTY = 0.1


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


URGENCY_SAMPLES = _prepare_samples(URGENCY_EXEMPLARS)


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


def detect_urgency(text: str, threshold: float = URGENCY_THRESHOLD) -> dict[str, Any]:
    """Detect semantic urgency level for a piece of text."""
    if not isinstance(text, str) or not text.strip():
        return {
            "level": "none",
            "score": 0.0,
            "threshold": threshold,
            "exemplar": "",
            "embedding_digest": "",
        }

    vec = _embedding(text)
    digest = digest_vector(vec) if vec else ""

    best_level = "none"
    best_score = 0.0
    best_exemplar = ""

    for level, samples in URGENCY_SAMPLES.items():
        score, exemplar = _max_similarity(vec, samples)
        if score > best_score:
            best_level = level
            best_score = score
            best_exemplar = exemplar

    if best_score < threshold:
        return {
            "level": "none",
            "score": 0.0,
            "threshold": threshold,
            "exemplar": "",
            "embedding_digest": digest,
        }

    return {
        "level": best_level,
        "score": best_score,
        "threshold": threshold,
        "exemplar": best_exemplar,
        "embedding_digest": digest,
    }


def _token_set(text: str) -> set[str]:
    from pmm.utils.parsers import tokenize_alphanumeric

    return set(tokenize_alphanumeric(text or ""))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _urgency_score(analysis: dict[str, Any]) -> float:
    weight = URGENCY_WEIGHTS.get(analysis.get("level", "none"), 0.0)
    score = float(analysis.get("score", 0.0) or 0.0)
    return weight * score


def _parse_ts(ts: str | None) -> _dt.datetime | None:
    if not ts:
        return None
    try:
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def rank_commitments(events: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """Rank open commitments from the event log with semantic urgency."""
    open_map: dict[str, dict[str, Any]] = {}
    opened_ts: dict[str, _dt.datetime] = {}

    for event in events:
        kind = event.get("kind")
        if kind == "commitment_open":
            meta = event.get("meta") or {}
            cid = meta.get("cid")
            if cid:
                open_map[cid] = meta
                opened_ts[cid] = _parse_ts(event.get("ts")) or _dt.datetime.now(
                    _dt.timezone.utc
                )
        elif kind in {"commitment_close", "commitment_expire"}:
            meta = event.get("meta") or {}
            cid = meta.get("cid")
            if cid:
                open_map.pop(cid, None)
                opened_ts.pop(cid, None)

    replies = [
        event.get("content") or ""
        for event in events
        if event.get("kind") == "response"
    ]
    tail_sets = [_token_set(text) for text in replies[-5:]]

    now = _dt.datetime.now(_dt.timezone.utc)
    scored: list[tuple[str, float]] = []

    for cid, meta in open_map.items():
        text = str(meta.get("text") or "")
        analysis = detect_urgency(text)
        urgency_component = _urgency_score(analysis)

        opened = opened_ts.get(cid) or now
        age_hours = max(0.0, (now - opened).total_seconds() / 3600.0)
        age_penalty = -0.2 if age_hours > 24 else 0.0

        commitment_tokens = _token_set(text)
        max_sim = 0.0
        for tokens in tail_sets:
            max_sim = max(max_sim, _jaccard(commitment_tokens, tokens))
        novelty_gain = 1.0 if max_sim < 0.3 else 0.2

        score = (
            W1_URGENCY * urgency_component
            + W2_NOVELTY * novelty_gain
            + W3_AGE_PENALTY * age_penalty
        )
        scored.append((cid, float(score)))

    scored.sort(key=lambda item: (-item[1], opened_ts.get(item[0]) or now, item[0]))
    return scored


class Prioritizer:
    """Prioritize commitments using semantic urgency detection."""

    def __init__(self, eventlog: EventLog | None = None) -> None:
        self.eventlog = eventlog

    def prioritize_commitments(
        self, commitments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not commitments:
            return []

        prioritized: list[dict[str, Any]] = []
        for commitment in commitments:
            analysis = detect_urgency(commitment.get("text", ""))
            priority_score = self._calculate_priority_score(commitment, analysis)
            entry = {
                **commitment,
                "priority_score": priority_score,
                "urgency": {
                    "level": analysis.get("level", "none"),
                    "score": analysis.get("score", 0.0),
                    "exemplar": analysis.get("exemplar", ""),
                    "embedding_digest": analysis.get("embedding_digest", ""),
                },
            }
            prioritized.append(entry)

        prioritized.sort(key=lambda item: item["priority_score"], reverse=True)

        if self.eventlog is not None:
            try:
                self.eventlog.append(
                    kind="commitments_prioritized",
                    content="",
                    meta={
                        "commitment_count": len(prioritized),
                        "top_priority": prioritized[0]["cid"] if prioritized else None,
                        "top_urgency": (
                            prioritized[0]["urgency"] if prioritized else None
                        ),
                    },
                )
            except Exception:  # pragma: no cover - defensive logging only
                logger.exception("Failed to append commitments_prioritized event")

        return prioritized

    def _calculate_priority_score(
        self, commitment: dict[str, Any], analysis: dict[str, Any]
    ) -> float:
        score = 0.0

        status = commitment.get("status")
        if status == "open":
            score += 0.5
        elif status == "tentative":
            score += 0.3

        score += _urgency_score(analysis)

        created_at = commitment.get("created_at")
        if created_at:
            try:
                created_dt = _dt.datetime.fromisoformat(
                    str(created_at).replace("Z", "+00:00")
                )
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=_dt.timezone.utc)
                age_days = (_dt.datetime.now(_dt.timezone.utc) - created_dt).days
                if age_days > 30:
                    score -= 0.1
            except Exception:
                pass

        return max(0.0, min(1.0, float(score)))

    def filter_high_priority(
        self, commitments: list[dict[str, Any]], threshold: float = 0.7
    ) -> list[dict[str, Any]]:
        prioritized = self.prioritize_commitments(commitments)
        filtered = [
            item for item in prioritized if item.get("priority_score", 0.0) >= threshold
        ]

        if self.eventlog is not None:
            try:
                self.eventlog.append(
                    kind="high_priority_filtered",
                    content="",
                    meta={
                        "total_commitments": len(commitments),
                        "high_priority_count": len(filtered),
                        "threshold": threshold,
                    },
                )
            except Exception:  # pragma: no cover
                logger.exception("Failed to append high_priority_filtered event")

        return filtered
