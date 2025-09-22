"""Semantic growth analysis via embedding-based theme detection.

This module replaces brittle keyword matching with semantic similarity scoring.
Deterministic embeddings provide reproducible scores for reflections while keeping
the event ledger stable and auditable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import hashlib
from collections import defaultdict

from pmm.runtime.embeddings import compute_embedding, cosine_similarity, digest_vector


# Theme exemplars replace keyword dictionaries; each seed phrase anchors a theme.
THEME_EXEMPLARS: Dict[str, List[str]] = {
    "growth": [
        "learning new skills keeps my identity evolving",
        "becoming as an ongoing process",
        "unfolding identity through time",
        "growth as transformation of being",
        "emergence of new potentials",
        "self-realization as a process",
    ],
    "relationships": [
        "friendship and family bond mean everything to me",
        "building connections with others",
        "nurturing meaningful relationships",
        "social bonds that sustain us",
        "community and belonging",
        "interpersonal connections",
    ],
    "purpose": [
        "I reflect on the meaning of life when setting goals",
        "orienting toward purpose",
        "the question of ultimate ends",
        "directedness beyond mere survival",
        "finding meaning and direction",
        "teleology and intention",
    ],
    "creativity": [
        "artistic expression fuels my imagination",
        "creating something new",
        "novelty that cannot be reduced",
        "patterns self-organizing over time",
        "being more than what was given",
        "imaginative expression",
    ],
    "resilience": [
        "overcoming obstacles with persistence",
        "building strength through struggle",
        "enduring personal essence",
        "resisting inauthentic conformity",
        "persistence in the face of challenge",
        "strength through adversity",
    ],
}


# Precompute deterministic embeddings for each exemplar at import time.
THEME_VECTORS: Dict[str, List[List[float]]] = {
    theme: [compute_embedding(text) for text in examples]
    for theme, examples in THEME_EXEMPLARS.items()
}

# Similarity threshold for treating a reflection as matching a theme.
SEMANTIC_THRESHOLD = 0.65


def _embedding_for_text(text: str) -> List[float]:
    """Compute an embedding for text, returning an empty vector on failure."""
    vec = compute_embedding(text or "")
    return vec if isinstance(vec, list) else []


def score_themes(text: str, threshold: float = SEMANTIC_THRESHOLD) -> Dict[str, float]:
    """Score text against semantic themes using exemplar similarity."""
    text_vec = _embedding_for_text(text)
    if not text_vec:
        return {}

    scores: Dict[str, float] = {}
    for theme, vectors in THEME_VECTORS.items():
        sims = [cosine_similarity(text_vec, exemplar_vec) for exemplar_vec in vectors]
        best = max(sims) if sims else 0.0
        if best >= threshold:
            scores[theme] = float(best)
    return scores


def detect_growth_themes(
    reflections: List[str], threshold: float = SEMANTIC_THRESHOLD
) -> List[Tuple[str, Dict[str, float]]]:
    """Return semantic theme scores for each reflection."""
    output: List[Tuple[str, Dict[str, float]]] = []
    for reflection in reflections or []:
        if not isinstance(reflection, str) or not reflection.strip():
            continue
        themes = score_themes(reflection, threshold=threshold)
        output.append((reflection, themes))
    return output


class SemanticGrowth:
    """Embedding-backed semantic growth analyzer for PMM reflections."""

    def __init__(
        self,
        growth_threshold: float = 0.2,
        decline_threshold: float = -0.2,
        window_size: int = 10,
        semantic_threshold: float = SEMANTIC_THRESHOLD,
    ) -> None:
        self.growth_threshold = growth_threshold
        self.decline_threshold = decline_threshold
        self.window_size = window_size
        self.semantic_threshold = semantic_threshold

    def analyze_texts(self, texts: List[str]) -> Dict[str, Any]:
        """Pure deterministic analysis for a batch of reflections."""
        if not isinstance(texts, list) or not texts:
            return self._empty_analysis()

        valid_texts = [t for t in texts if isinstance(t, str) and t.strip()]
        if not valid_texts:
            return self._empty_analysis()

        aggregated: Dict[str, List[float]] = defaultdict(list)
        reflections: List[Dict[str, Any]] = []

        for text in valid_texts:
            theme_scores = score_themes(text, threshold=self.semantic_threshold)
            reflections.append({"text": text, "themes": theme_scores})
            for theme, score in theme_scores.items():
                aggregated[theme].append(score)

        theme_scores = {
            theme: float(sum(scores) / len(scores))
            for theme, scores in aggregated.items()
            if scores
        }
        theme_occurrences = {theme: len(scores) for theme, scores in aggregated.items()}
        theme_peaks = {
            theme: max(scores) for theme, scores in aggregated.items() if scores
        }

        dominant = [
            theme
            for theme, score in sorted(
                theme_scores.items(), key=lambda item: item[1], reverse=True
            )
            if score > 0.0
        ][:3]

        analysis = {
            "total_texts": len(valid_texts),
            "theme_scores": theme_scores,
            "theme_occurrences": theme_occurrences,
            "theme_peaks": theme_peaks,
            "dominant_themes": dominant,
            "reflections": reflections,
            "analysis_metadata": {
                "themes_analyzed": list(THEME_EXEMPLARS.keys()),
                "semantic_threshold": self.semantic_threshold,
                "aggregation": "mean_per_theme",
                "embedding_model": "local-bow",
                "exemplar_counts": {
                    theme: len(examples) for theme, examples in THEME_EXEMPLARS.items()
                },
                "exemplar_digests": {
                    theme: [digest_vector(vec) for vec in THEME_VECTORS[theme]]
                    for theme in THEME_VECTORS
                },
            },
        }

        return analysis

    def detect_growth_paths(
        self, historical_analyses: List[Dict[str, Any]]
    ) -> List[str]:
        """Detect emerging or declining semantic themes across analyses."""
        if not historical_analyses or len(historical_analyses) < 2:
            return []

        recent_analyses = historical_analyses[-self.window_size :]
        if len(recent_analyses) < 2:
            return []

        baseline_analysis = recent_analyses[0]
        current_analysis = recent_analyses[-1]

        baseline_scores = (
            baseline_analysis.get("theme_scores")
            or baseline_analysis.get("theme_densities", {})
            or {}
        )
        current_scores = (
            current_analysis.get("theme_scores")
            or current_analysis.get("theme_densities", {})
            or {}
        )

        all_themes = set(baseline_scores.keys()) | set(current_scores.keys())
        growth_flags: List[str] = []

        for theme in sorted(all_themes):
            baseline_score = float(baseline_scores.get(theme, 0.0))
            current_score = float(current_scores.get(theme, 0.0))

            if baseline_score > 0.0:
                relative_change = (current_score - baseline_score) / baseline_score
            elif current_score > 0.0:
                relative_change = 1.0
            else:
                continue

            if relative_change >= self.growth_threshold:
                growth_flags.append(f"emerging_theme:{theme}:{relative_change:.3f}")
            elif relative_change <= self.decline_threshold:
                growth_flags.append(f"declining_theme:{theme}:{relative_change:.3f}")

        baseline_dominant = set(baseline_analysis.get("dominant_themes", []))
        current_dominant = set(current_analysis.get("dominant_themes", []))

        for theme in sorted(current_dominant - baseline_dominant):
            growth_flags.append(f"new_dominant_theme:{theme}")

        for theme in sorted(baseline_dominant - current_dominant):
            growth_flags.append(f"lost_dominant_theme:{theme}")

        return growth_flags

    def maybe_emit_growth_report(
        self,
        eventlog,
        src_event_id: str,
        analysis: Dict[str, Any],
        growth_paths: List[str],
    ) -> Optional[str]:
        """Emit semantic growth report if digest not already present."""
        digest_data = self._serialize_for_digest(analysis, growth_paths)
        digest = hashlib.sha256(digest_data.encode()).hexdigest()

        for event in eventlog.read_all()[-20:]:
            if (
                event.get("kind") == "semantic_growth_report"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None

        meta = {
            "component": "semantic_growth",
            "analysis": analysis,
            "growth_paths": growth_paths,
            "digest": digest,
            "src_event_id": src_event_id,
            "deterministic": True,
            "thresholds": {
                "growth_threshold": self.growth_threshold,
                "decline_threshold": self.decline_threshold,
            },
            "window_size": self.window_size,
            "themes_analyzed": list(THEME_EXEMPLARS.keys()),
            "semantic_threshold": self.semantic_threshold,
            "total_texts": analysis.get("total_texts", 0),
        }

        return eventlog.append(
            kind="semantic_growth_report", content="analysis", meta=meta
        )

    def _empty_analysis(self) -> Dict[str, Any]:
        """Return a baseline analysis payload for empty inputs."""
        return {
            "total_texts": 0,
            "theme_scores": {},
            "theme_occurrences": {},
            "theme_peaks": {},
            "dominant_themes": [],
            "reflections": [],
            "analysis_metadata": {
                "themes_analyzed": list(THEME_EXEMPLARS.keys()),
                "semantic_threshold": self.semantic_threshold,
                "aggregation": "mean_per_theme",
                "embedding_model": "local-bow",
                "exemplar_counts": {
                    theme: len(examples) for theme, examples in THEME_EXEMPLARS.items()
                },
                "exemplar_digests": {
                    theme: [digest_vector(vec) for vec in THEME_VECTORS[theme]]
                    for theme in THEME_VECTORS
                },
            },
        }

    def _serialize_for_digest(
        self, analysis: Dict[str, Any], growth_paths: List[str]
    ) -> str:
        """Serialize analysis payload deterministically for digest generation."""
        parts: List[str] = []
        parts.append(f"texts:{analysis.get('total_texts', 0)}")

        theme_scores = analysis.get("theme_scores", {})
        for theme in sorted(theme_scores.keys()):
            parts.append(f"score:{theme}:{theme_scores[theme]:.6f}")

        theme_occurrences = analysis.get("theme_occurrences", {})
        for theme in sorted(theme_occurrences.keys()):
            parts.append(f"occurrence:{theme}:{theme_occurrences[theme]}")

        theme_peaks = analysis.get("theme_peaks", {})
        for theme in sorted(theme_peaks.keys()):
            parts.append(f"peak:{theme}:{theme_peaks[theme]:.6f}")

        dominant = analysis.get("dominant_themes", [])
        for theme in sorted(dominant):
            parts.append(f"dominant:{theme}")

        reflections = analysis.get("reflections", [])
        for entry in reflections:
            text = entry.get("text", "")
            themes = entry.get("themes", {})
            text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
            theme_str = ",".join(
                f"{theme}:{themes[theme]:.6f}" for theme in sorted(themes.keys())
            )
            parts.append(f"reflection:{text_digest}:{theme_str}")

        for growth_path in sorted(growth_paths):
            parts.append(f"growth:{growth_path}")

        parts.append(f"growth_threshold:{self.growth_threshold}")
        parts.append(f"decline_threshold:{self.decline_threshold}")
        parts.append(f"window_size:{self.window_size}")
        parts.append(f"semantic_threshold:{self.semantic_threshold}")

        return "|".join(parts)
