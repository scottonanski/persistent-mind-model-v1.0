"""Semantic Growth System for PMM.

Deterministic semantic clustering and growth trajectory detection that enables
the PMM to detect and leverage semantic themes in commitments and reflections,
building long-range growth trajectories with full ledger integrity.
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional
import hashlib
import re
from collections import Counter


class SemanticGrowth:
    """
    Deterministic semantic growth analysis for detecting and tracking semantic themes
    in PMM commitments and reflections over time. Maintains full auditability through
    the event ledger.
    """

    # Deterministic semantic theme categories with fixed keyword dictionaries
    SEMANTIC_THEMES = {
        "learning": {
            "keywords": [
                "learn",
                "study",
                "understand",
                "discover",
                "explore",
                "research",
                "knowledge",
                "skill",
                "practice",
                "improve",
                "develop",
                "master",
                "education",
                "training",
                "growth",
                "progress",
                "advancement",
            ],
            "weight": 1.0,
        },
        "creativity": {
            "keywords": [
                "create",
                "design",
                "build",
                "make",
                "craft",
                "innovate",
                "invent",
                "artistic",
                "creative",
                "imagination",
                "original",
                "novel",
                "unique",
                "express",
                "inspire",
                "vision",
                "aesthetic",
                "beauty",
            ],
            "weight": 1.0,
        },
        "relationships": {
            "keywords": [
                "connect",
                "relationship",
                "friend",
                "family",
                "community",
                "social",
                "collaborate",
                "team",
                "together",
                "share",
                "support",
                "help",
                "empathy",
                "compassion",
                "love",
                "trust",
                "bond",
                "network",
            ],
            "weight": 1.0,
        },
        "achievement": {
            "keywords": [
                "achieve",
                "accomplish",
                "succeed",
                "complete",
                "finish",
                "goal",
                "target",
                "objective",
                "milestone",
                "victory",
                "win",
                "excel",
                "performance",
                "result",
                "outcome",
                "success",
                "triumph",
            ],
            "weight": 1.0,
        },
        "reflection": {
            "keywords": [
                "reflect",
                "think",
                "consider",
                "contemplate",
                "ponder",
                "analyze",
                "evaluate",
                "assess",
                "review",
                "examine",
                "introspect",
                "meditate",
                "mindful",
                "awareness",
                "conscious",
                "insight",
                "wisdom",
            ],
            "weight": 1.0,
        },
        "health": {
            "keywords": [
                "health",
                "wellness",
                "fitness",
                "exercise",
                "nutrition",
                "sleep",
                "mental",
                "physical",
                "wellbeing",
                "balance",
                "energy",
                "vitality",
                "strength",
                "endurance",
                "recovery",
                "healing",
                "care",
            ],
            "weight": 1.0,
        },
        "productivity": {
            "keywords": [
                "productive",
                "efficient",
                "organize",
                "plan",
                "schedule",
                "manage",
                "focus",
                "concentrate",
                "discipline",
                "habit",
                "routine",
                "system",
                "workflow",
                "process",
                "optimize",
                "streamline",
                "effective",
            ],
            "weight": 1.0,
        },
        "spirituality": {
            "keywords": [
                "spiritual",
                "meaning",
                "purpose",
                "values",
                "beliefs",
                "faith",
                "transcendent",
                "sacred",
                "divine",
                "soul",
                "inner",
                "peace",
                "gratitude",
                "mindfulness",
                "presence",
                "connection",
                "unity",
            ],
            "weight": 1.0,
        },
    }

    def __init__(
        self,
        growth_threshold: float = 0.2,
        decline_threshold: float = -0.2,
        window_size: int = 10,
    ):
        """Initialize semantic growth analyzer.

        Args:
            growth_threshold: Minimum relative change to flag as emerging theme
            decline_threshold: Maximum relative change to flag as declining theme
            window_size: Number of recent texts to analyze for growth detection
        """
        self.growth_threshold = growth_threshold
        self.decline_threshold = decline_threshold
        self.window_size = window_size

    def analyze_texts(self, texts: List[str]) -> Dict[str, Any]:
        """
        Pure function.
        Extract semantic themes and clusters from a list of texts using deterministic
        keyword matching and normalization.

        Args:
            texts: List of text strings to analyze

        Returns:
            Analysis dict with theme counts, clusters, and metadata
        """
        if not texts or not isinstance(texts, list):
            return {
                "total_texts": 0,
                "theme_counts": {},
                "theme_densities": {},
                "dominant_themes": [],
                "analysis_metadata": {
                    "themes_analyzed": list(self.SEMANTIC_THEMES.keys()),
                    "normalization": "lowercase_word_boundary",
                    "total_keywords": sum(
                        len(theme["keywords"])
                        for theme in self.SEMANTIC_THEMES.values()
                    ),
                },
            }

        # Normalize and analyze each text
        all_theme_counts = Counter()
        total_words = 0

        for text in texts:
            if not text or not isinstance(text, str):
                continue

            normalized_text = self._normalize_text(text)
            words = normalized_text.split()
            total_words += len(words)

            # Count theme keywords in this text
            text_theme_counts = self._extract_themes(normalized_text)
            all_theme_counts.update(text_theme_counts)

        # Calculate theme densities (themes per word)
        theme_densities = {}
        for theme, count in all_theme_counts.items():
            theme_densities[theme] = count / max(total_words, 1)

        # Identify dominant themes (top 3 by density)
        sorted_themes = sorted(
            theme_densities.items(), key=lambda x: x[1], reverse=True
        )
        dominant_themes = [theme for theme, density in sorted_themes[:3] if density > 0]

        return {
            "total_texts": len([t for t in texts if t and isinstance(t, str)]),
            "theme_counts": dict(all_theme_counts),
            "theme_densities": theme_densities,
            "dominant_themes": dominant_themes,
            "analysis_metadata": {
                "themes_analyzed": list(self.SEMANTIC_THEMES.keys()),
                "normalization": "lowercase_word_boundary",
                "total_keywords": sum(
                    len(theme["keywords"]) for theme in self.SEMANTIC_THEMES.values()
                ),
                "total_words": total_words,
            },
        }

    def detect_growth_paths(
        self, historical_analyses: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Pure function.
        Compare theme clusters over time to detect emerging or declining themes.

        Args:
            historical_analyses: List of analysis dicts from analyze_texts()

        Returns:
            List of growth path flags (empty if none detected)
        """
        if not historical_analyses or len(historical_analyses) < 2:
            return []

        growth_flags = []

        # Analyze recent window of analyses
        recent_analyses = historical_analyses[-self.window_size :]

        if len(recent_analyses) < 2:
            return []

        # Compare first and last analysis in window for growth detection
        baseline_analysis = recent_analyses[0]
        current_analysis = recent_analyses[-1]

        baseline_densities = baseline_analysis.get("theme_densities", {})
        current_densities = current_analysis.get("theme_densities", {})

        # Calculate relative changes for each theme
        all_themes = set(baseline_densities.keys()) | set(current_densities.keys())

        for theme in all_themes:
            baseline_density = baseline_densities.get(theme, 0.0)
            current_density = current_densities.get(theme, 0.0)

            # Calculate relative change (handle division by zero)
            if baseline_density > 0:
                relative_change = (
                    current_density - baseline_density
                ) / baseline_density
            elif current_density > 0:
                relative_change = 1.0  # New theme emergence
            else:
                continue  # Both zero, no change

            # Flag significant changes
            if relative_change >= self.growth_threshold:
                growth_flags.append(f"emerging_theme:{theme}:{relative_change:.3f}")
            elif relative_change <= self.decline_threshold:
                growth_flags.append(f"declining_theme:{theme}:{relative_change:.3f}")

        # Detect dominant theme shifts
        baseline_dominant = set(baseline_analysis.get("dominant_themes", []))
        current_dominant = set(current_analysis.get("dominant_themes", []))

        new_dominant = current_dominant - baseline_dominant
        lost_dominant = baseline_dominant - current_dominant

        for theme in new_dominant:
            growth_flags.append(f"new_dominant_theme:{theme}")

        for theme in lost_dominant:
            growth_flags.append(f"lost_dominant_theme:{theme}")

        return growth_flags

    def maybe_emit_growth_report(
        self,
        eventlog,
        src_event_id: str,
        analysis: Dict[str, Any],
        growth_paths: List[str],
    ) -> Optional[str]:
        """
        Emit semantic_growth_report event with digest deduplication.
        Event shape:
          kind="semantic_growth_report"
          content="analysis"
          meta={
            "component": "semantic_growth",
            "analysis": analysis,
            "growth_paths": growth_paths,
            "digest": <SHA256 over analysis + growth_paths>,
            "src_event_id": src_event_id,
            "deterministic": True,
            "thresholds": {growth_threshold, decline_threshold},
            "window_size": window_size
          }
        Returns event id or None if skipped due to idempotency.
        """
        # Generate deterministic digest
        digest_data = self._serialize_for_digest(analysis, growth_paths)
        digest = hashlib.sha256(digest_data.encode()).hexdigest()

        # Check for existing event with same digest (idempotency)
        all_events = eventlog.read_all()
        for event in all_events[-20:]:  # Check recent events for efficiency
            if (
                event.get("kind") == "semantic_growth_report"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None  # Skip - already exists

        # Prepare event metadata
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
            "themes_analyzed": list(self.SEMANTIC_THEMES.keys()),
            "total_texts": analysis.get("total_texts", 0),
        }

        # Emit the growth report event
        event_id = eventlog.append(
            kind="semantic_growth_report", content="analysis", meta=meta
        )

        return event_id

    def _normalize_text(self, text: str) -> str:
        """Normalize text deterministically: lowercase, preserve word boundaries."""
        # Convert to lowercase but preserve punctuation for word boundary detection
        normalized = text.lower().strip()

        # Compact multiple whitespace but preserve single spaces
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized

    def _extract_themes(self, normalized_text: str) -> Counter:
        """Extract theme counts from normalized text using keyword matching."""
        theme_counts = Counter()

        for theme_name, theme_data in self.SEMANTIC_THEMES.items():
            keywords = theme_data["keywords"]
            weight = theme_data["weight"]

            for keyword in keywords:
                # Use word boundary matching to avoid partial matches
                pattern = r"\b" + re.escape(keyword) + r"\b"
                matches = len(re.findall(pattern, normalized_text))
                if matches > 0:
                    theme_counts[theme_name] += matches * weight

        return theme_counts

    def _serialize_for_digest(
        self, analysis: Dict[str, Any], growth_paths: List[str]
    ) -> str:
        """Serialize analysis and growth paths deterministically for digest generation."""
        parts = []

        # Add total texts
        parts.append(f"texts:{analysis.get('total_texts', 0)}")

        # Add theme counts in sorted order
        theme_counts = analysis.get("theme_counts", {})
        for theme in sorted(theme_counts.keys()):
            count = theme_counts[theme]
            parts.append(f"theme:{theme}:{count}")

        # Add theme densities in sorted order
        theme_densities = analysis.get("theme_densities", {})
        for theme in sorted(theme_densities.keys()):
            density = theme_densities[theme]
            parts.append(f"density:{theme}:{density:.6f}")

        # Add dominant themes in sorted order
        dominant_themes = analysis.get("dominant_themes", [])
        for theme in sorted(dominant_themes):
            parts.append(f"dominant:{theme}")

        # Add growth paths in sorted order
        for growth_path in sorted(growth_paths):
            parts.append(f"growth:{growth_path}")

        # Add configuration
        parts.append(f"growth_threshold:{self.growth_threshold}")
        parts.append(f"decline_threshold:{self.decline_threshold}")
        parts.append(f"window_size:{self.window_size}")

        return "|".join(parts)
