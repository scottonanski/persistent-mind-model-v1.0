"""Semantic meta-reflection analysis for PMM.

Replaces keyword heuristics with embedding-backed scoring for reflection depth,
follow-through, evolution, and stance while preserving deterministic logging and
anomaly detection semantics.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from pmm.runtime.embeddings import compute_embedding, cosine_similarity, digest_vector
from pmm.runtime.filters.stance_filter import STANCE_THRESHOLD, detect_stance


# Reflection exemplars grouped by dimension and qualitative label.
REFLECTION_EXEMPLARS: Dict[str, Dict[str, List[str]]] = {
    "depth": {
        "shallow": [
            "this is simple",
            "just a small thought",
            "surface level reflection",
        ],
        "deep": [
            "thinking about the root cause",
            "considering long term implications",
            "philosophical analysis",
        ],
    },
    "follow_through": {
        "low": [
            "I might do this",
            "not sure if I will follow through",
            "maybe someday",
        ],
        "high": [
            "I will take concrete steps",
            "this is my next action",
            "I am committed to this plan",
        ],
    },
    "evolution": {
        "stagnant": [
            "I feel the same as always",
            "nothing has changed",
            "repeating the same ideas",
        ],
        "growing": [
            "I have learned from past mistakes",
            "my perspective is changing",
            "this shows progress",
        ],
    },
}

# Default similarity threshold for classifying reflection dimensions.
REFLECTION_THRESHOLD = 0.60


def _embedding_for_text(text: str) -> List[float]:
    vec = compute_embedding(text or "")
    return vec if isinstance(vec, list) else []


def _score_dimension(
    text_vec: List[float],
    vectors: Dict[str, List[List[float]]],
    threshold: float,
) -> Tuple[str, float, Dict[str, float]]:
    """Return (label, score, per-label scores) for a reflection dimension."""
    label_scores: Dict[str, float] = {}
    best_label = "neutral"
    best_score = 0.0

    if not text_vec:
        return best_label, best_score, label_scores

    for label, exemplar_vecs in vectors.items():
        sims = [
            cosine_similarity(text_vec, exemplar_vec)
            for exemplar_vec in exemplar_vecs
            if exemplar_vec
        ]
        best = max(sims) if sims else 0.0
        label_scores[label] = float(best)
        if best > best_score:
            best_label = label
            best_score = float(best)

    if best_score < threshold:
        return "neutral", 0.0, label_scores

    return best_label, best_score, label_scores


# Pre-compute exemplar embeddings so scoring remains deterministic at runtime.
DIMENSION_VECTORS: Dict[str, Dict[str, List[List[float]]]] = {
    dimension: {
        label: [
            vec
            for vec in (_embedding_for_text(example) for example in exemplar_texts)
            if vec
        ]
        for label, exemplar_texts in labels.items()
    }
    for dimension, labels in REFLECTION_EXEMPLARS.items()
}


def score_reflection(
    text: str, semantic_threshold: float = REFLECTION_THRESHOLD
) -> Dict[str, Any]:
    """Produce semantic scores for a single reflection text."""
    text_vec = _embedding_for_text(text)
    embedding_digest = digest_vector(text_vec) if text_vec else ""

    dimension_results: Dict[str, Dict[str, Any]] = {}
    for dimension, vectors in DIMENSION_VECTORS.items():
        label, score, scores = _score_dimension(text_vec, vectors, semantic_threshold)
        dimension_results[dimension] = {
            "label": label,
            "score": score,
            "scores": scores,
        }

    stance_label, stance_score = detect_stance(text)

    return {
        "text": text,
        "embedding_digest": embedding_digest,
        "stance": {"label": stance_label, "score": stance_score},
        "dimensions": dimension_results,
    }


class MetaReflection:
    """Embedding-backed meta reflection analyzer."""

    def __init__(
        self,
        bias_threshold: float = 0.7,
        shallow_threshold: float = 0.6,
        semantic_threshold: float = REFLECTION_THRESHOLD,
    ) -> None:
        self.bias_threshold = max(0.0, min(1.0, bias_threshold))
        self.shallow_threshold = max(0.0, min(1.0, shallow_threshold))
        self.semantic_threshold = max(0.0, min(1.0, semantic_threshold))

    def analyze_reflections(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze reflection events and return semantic summary metrics."""
        if not isinstance(events, list) or not events:
            return self._empty_summary()

        reflections: List[str] = []
        for event in events:
            if isinstance(event, dict) and event.get("kind") == "reflection":
                content = event.get("content", "")
                if isinstance(content, str) and content.strip():
                    reflections.append(content.strip())

        if not reflections:
            return self._empty_summary()

        reflection_analyses = [
            score_reflection(text, semantic_threshold=self.semantic_threshold)
            for text in reflections
        ]

        stance_metrics = self._aggregate_stance(reflection_analyses)
        dimension_metrics = self._aggregate_dimensions(reflection_analyses)

        summary = {
            "reflection_count": len(reflection_analyses),
            "stance_metrics": stance_metrics,
            "dimension_metrics": dimension_metrics,
            "reflections": reflection_analyses,
            "analysis_metadata": self._analysis_metadata(),
        }

        return summary

    def detect_meta_anomalies(self, summary: Dict[str, Any]) -> List[str]:
        """Detect anomalies based on semantic summary metrics."""
        if not isinstance(summary, dict) or summary.get("reflection_count", 0) == 0:
            return []

        anomalies: List[str] = []
        reflection_count = summary["reflection_count"]

        stance_metrics = summary.get("stance_metrics", {})
        dominant_stance = stance_metrics.get("dominant_label")
        dominant_ratio = stance_metrics.get("dominant_ratio", 0.0)
        if (
            dominant_stance
            and dominant_stance != "neutral"
            and dominant_ratio >= self.bias_threshold
        ):
            anomalies.append(f"stance_bias:{dominant_stance}:{dominant_ratio:.3f}")

        dimension_metrics = summary.get("dimension_metrics", {})

        depth_metrics = dimension_metrics.get("depth", {})
        shallow_ratio = depth_metrics.get("distribution", {}).get("shallow", 0.0)
        depth_avg = depth_metrics.get("avg_score", 0.0)
        if shallow_ratio >= self.shallow_threshold:
            anomalies.append(f"shallow_reflection_pattern:{shallow_ratio:.3f}")
        if depth_avg < 0.3 and reflection_count >= 3:
            anomalies.append(f"low_depth_score:{depth_avg:.3f}")

        follow_metrics = dimension_metrics.get("follow_through", {})
        high_follow_ratio = follow_metrics.get("distribution", {}).get("high", 0.0)
        if reflection_count >= 3 and high_follow_ratio < 0.3:
            anomalies.append(f"low_follow_through:{high_follow_ratio:.3f}")

        evolution_metrics = dimension_metrics.get("evolution", {})
        growing_ratio = evolution_metrics.get("distribution", {}).get("growing", 0.0)
        if reflection_count >= 5 and growing_ratio < 0.3:
            anomalies.append(f"stagnant_evolution:{growing_ratio:.3f}")

        return anomalies

    def maybe_emit_report(
        self,
        eventlog,
        summary: Dict[str, Any],
        window: str,
    ) -> Optional[str]:
        """Emit meta reflection report with digest deduplication."""
        anomalies = self.detect_meta_anomalies(summary)
        digest_data = self._serialize_for_digest(summary, anomalies, window)
        digest = hashlib.sha256(digest_data.encode()).hexdigest()

        for event in eventlog.read_all()[-20:]:
            if (
                event.get("kind") == "meta_reflection_report"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None

        meta = {
            "component": "meta_reflection",
            "summary": summary,
            "anomalies": anomalies,
            "window": window,
            "digest": digest,
            "deterministic": True,
            "bias_threshold": self.bias_threshold,
            "shallow_threshold": self.shallow_threshold,
            "semantic_threshold": self.semantic_threshold,
            "reflection_count": summary.get("reflection_count", 0),
        }

        return eventlog.append(
            kind="meta_reflection_report", content="meta_analysis", meta=meta
        )

    def _aggregate_stance(self, reflections: List[Dict[str, Any]]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        score_sum = 0.0

        for analysis in reflections:
            stance = analysis.get("stance", {})
            label = stance.get("label", "neutral")
            score = float(stance.get("score", 0.0) or 0.0)
            counts[label] = counts.get(label, 0) + 1
            score_sum += score

        total = len(reflections)
        distribution = {
            label: count / total for label, count in counts.items() if total > 0
        }
        dominant_label = max(counts, key=counts.get) if counts else "neutral"
        dominant_ratio = counts.get(dominant_label, 0) / total if total > 0 else 0.0

        return {
            "distribution": distribution,
            "avg_score": score_sum / total if total > 0 else 0.0,
            "dominant_label": dominant_label,
            "dominant_ratio": dominant_ratio,
        }

    def _aggregate_dimensions(
        self, reflections: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        totals: Dict[str, Dict[str, Any]] = {}
        total = len(reflections)

        for analysis in reflections:
            dimensions = analysis.get("dimensions", {})
            for dimension, detail in dimensions.items():
                label = detail.get("label", "neutral")
                score = float(detail.get("score", 0.0) or 0.0)
                record = totals.setdefault(
                    dimension,
                    {
                        "counts": {},
                        "score_sum": 0.0,
                        "high_confidence": 0,
                    },
                )
                record["counts"][label] = record["counts"].get(label, 0) + 1
                record["score_sum"] += score
                if score >= self.semantic_threshold:
                    record["high_confidence"] += 1

        metrics: Dict[str, Dict[str, Any]] = {}
        for dimension, record in totals.items():
            counts = record["counts"]
            distribution = {
                label: count / total for label, count in counts.items() if total > 0
            }
            dominant_label = max(counts, key=counts.get) if counts else "neutral"
            dominant_ratio = counts.get(dominant_label, 0) / total if total > 0 else 0.0
            metrics[dimension] = {
                "distribution": distribution,
                "avg_score": record["score_sum"] / total if total > 0 else 0.0,
                "high_confidence_ratio": (
                    record["high_confidence"] / total if total > 0 else 0.0
                ),
                "dominant_label": dominant_label,
                "dominant_ratio": dominant_ratio,
            }

        return metrics

    def _analysis_metadata(self) -> Dict[str, Any]:
        return {
            "semantic_threshold": self.semantic_threshold,
            "stance_threshold": STANCE_THRESHOLD,
            "dimensions": sorted(REFLECTION_EXEMPLARS.keys()),
            "exemplar_counts": {
                dimension: {label: len(examples) for label, examples in labels.items()}
                for dimension, labels in REFLECTION_EXEMPLARS.items()
            },
            "exemplar_digests": {
                dimension: {
                    label: [
                        digest_vector(vec)
                        for vec in DIMENSION_VECTORS[dimension][label]
                    ]
                    for label in labels.keys()
                }
                for dimension, labels in REFLECTION_EXEMPLARS.items()
            },
        }

    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "reflection_count": 0,
            "stance_metrics": {
                "distribution": {},
                "avg_score": 0.0,
                "dominant_label": "neutral",
                "dominant_ratio": 0.0,
            },
            "dimension_metrics": {},
            "reflections": [],
            "analysis_metadata": self._analysis_metadata(),
        }

    def _serialize_for_digest(
        self,
        summary: Dict[str, Any],
        anomalies: List[str],
        window: str,
    ) -> str:
        parts: List[str] = []
        parts.append(f"window:{window}")
        parts.append(f"reflection_count:{summary.get('reflection_count', 0)}")

        stance_metrics = summary.get("stance_metrics", {})
        parts.append(
            f"stance_dominant:{stance_metrics.get('dominant_label', 'neutral')}:{stance_metrics.get('dominant_ratio', 0.0):.6f}"
        )
        for label in sorted(stance_metrics.get("distribution", {}).keys()):
            ratio = stance_metrics["distribution"][label]
            parts.append(f"stance_dist:{label}:{ratio:.6f}")
        parts.append(f"stance_avg_score:{stance_metrics.get('avg_score', 0.0):.6f}")

        dimension_metrics = summary.get("dimension_metrics", {})
        for dimension in sorted(dimension_metrics.keys()):
            metrics = dimension_metrics[dimension]
            parts.append(
                f"dimension:{dimension}:{metrics.get('dominant_label', 'neutral')}:{metrics.get('dominant_ratio', 0.0):.6f}"
            )
            parts.append(
                f"dimension_avg:{dimension}:{metrics.get('avg_score', 0.0):.6f}"
            )
            parts.append(
                f"dimension_high_confidence:{dimension}:{metrics.get('high_confidence_ratio', 0.0):.6f}"
            )
            for label in sorted(metrics.get("distribution", {}).keys()):
                ratio = metrics["distribution"][label]
                parts.append(f"dimension_dist:{dimension}:{label}:{ratio:.6f}")

        reflections = summary.get("reflections", [])
        for idx, analysis in enumerate(reflections):
            digest = analysis.get("embedding_digest", "")
            parts.append(f"reflection:{idx}:{digest}")
            stance = analysis.get("stance", {})
            parts.append(
                f"reflection_stance:{idx}:{stance.get('label', 'neutral')}:{float(stance.get('score', 0.0) or 0.0):.6f}"
            )
            dimensions = analysis.get("dimensions", {})
            for dimension in sorted(dimensions.keys()):
                detail = dimensions[dimension]
                parts.append(
                    f"reflection_dimension:{idx}:{dimension}:{detail.get('label', 'neutral')}:{float(detail.get('score', 0.0) or 0.0):.6f}"
                )

        for anomaly in sorted(anomalies):
            parts.append(f"anomaly:{anomaly}")

        parts.append(f"bias_threshold:{self.bias_threshold:.6f}")
        parts.append(f"shallow_threshold:{self.shallow_threshold:.6f}")
        parts.append(f"semantic_threshold:{self.semantic_threshold:.6f}")

        return "|".join(parts)
