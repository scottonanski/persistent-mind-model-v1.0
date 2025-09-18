"""Meta-Reflection System for PMM.

Deterministic, event-driven system that analyzes reflections themselves across time,
detects biases and limitations, and generates higher-order self-assessments with
full ledger integrity and CONTRIBUTING.md compliance.
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional
import hashlib
import re
from collections import Counter


class MetaReflection:
    """
    Deterministic meta-reflection system that analyzes reflection patterns over time
    to detect biases, limitations, and generate higher-order self-assessments.
    """

    # Deterministic bias detection keywords for stance analysis
    STANCE_KEYWORDS = {
        "positive": [
            "good",
            "great",
            "excellent",
            "amazing",
            "wonderful",
            "fantastic",
            "successful",
            "accomplished",
            "proud",
            "satisfied",
            "happy",
            "excited",
            "confident",
            "optimistic",
            "motivated",
            "inspired",
            "grateful",
        ],
        "negative": [
            "bad",
            "terrible",
            "awful",
            "horrible",
            "disappointing",
            "failed",
            "frustrated",
            "angry",
            "sad",
            "worried",
            "anxious",
            "stressed",
            "overwhelmed",
            "discouraged",
            "pessimistic",
            "doubtful",
            "regret",
        ],
        "neutral": [
            "okay",
            "fine",
            "normal",
            "average",
            "standard",
            "typical",
            "usual",
            "moderate",
            "balanced",
            "mixed",
            "uncertain",
            "unclear",
            "thinking",
            "considering",
            "evaluating",
            "analyzing",
            "observing",
            "noting",
        ],
    }

    # Depth indicators for reflection quality assessment
    DEPTH_INDICATORS = {
        "shallow": [
            "just",
            "simply",
            "only",
            "basically",
            "obviously",
            "clearly",
            "easy",
            "quick",
            "brief",
            "short",
            "surface",
            "simple",
        ],
        "deep": [
            "complex",
            "nuanced",
            "intricate",
            "sophisticated",
            "profound",
            "comprehensive",
            "thorough",
            "detailed",
            "elaborate",
            "multifaceted",
            "underlying",
            "fundamental",
            "root",
            "core",
            "essence",
            "implications",
            "consequences",
            "ramifications",
            "interconnected",
            "systemic",
        ],
    }

    def __init__(self, bias_threshold: float = 0.7, shallow_threshold: float = 0.6):
        """Initialize meta-reflection analyzer.

        Args:
            bias_threshold: Threshold for detecting stance bias (0.0-1.0)
            shallow_threshold: Threshold for detecting shallow reflections (0.0-1.0)
        """
        self.bias_threshold = max(0.0, min(1.0, bias_threshold))
        self.shallow_threshold = max(0.0, min(1.0, shallow_threshold))

    def analyze_reflections(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Pure function.
        Analyze reflection events to extract meta-patterns, biases, and depth metrics.

        Args:
            events: List of event dictionaries from event log

        Returns:
            MetaReflectionSummary dict with bias metrics, depth scores, and patterns
        """
        if not events or not isinstance(events, list):
            return {
                "reflection_count": 0,
                "bias_metrics": {
                    "positive_ratio": 0.0,
                    "negative_ratio": 0.0,
                    "neutral_ratio": 0.0,
                    "stance_skew": 0.0,
                },
                "depth_metrics": {
                    "avg_token_length": 0.0,
                    "shallow_ratio": 0.0,
                    "deep_ratio": 0.0,
                    "depth_score": 0.0,
                },
                "closure_metrics": {
                    "commitment_mentions": 0,
                    "follow_through_ratio": 0.0,
                    "evolution_indicators": 0,
                },
                "repetition_metrics": {
                    "unique_themes": 0,
                    "repetition_ratio": 0.0,
                    "diversity_score": 0.0,
                },
            }

        # Filter reflection events
        reflection_events = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("kind") == "reflection":
                reflection_events.append(event)

        if not reflection_events:
            return self._empty_summary()

        # Extract reflection texts
        reflection_texts = []
        for event in reflection_events:
            content = event.get("content", "")
            if isinstance(content, str) and content.strip():
                reflection_texts.append(content.strip())

        if not reflection_texts:
            return self._empty_summary()

        # Analyze bias patterns
        bias_metrics = self._analyze_bias_patterns(reflection_texts)

        # Analyze depth patterns
        depth_metrics = self._analyze_depth_patterns(reflection_texts)

        # Analyze closure patterns
        closure_metrics = self._analyze_closure_patterns(reflection_texts, events)

        # Analyze repetition patterns
        repetition_metrics = self._analyze_repetition_patterns(reflection_texts)

        return {
            "reflection_count": len(reflection_texts),
            "bias_metrics": bias_metrics,
            "depth_metrics": depth_metrics,
            "closure_metrics": closure_metrics,
            "repetition_metrics": repetition_metrics,
        }

    def detect_meta_anomalies(self, summary: Dict[str, Any]) -> List[str]:
        """
        Pure function.
        Detect meta-anomalies in reflection patterns based on summary metrics.

        Args:
            summary: MetaReflectionSummary from analyze_reflections()

        Returns:
            List of anomaly flags
        """
        anomalies = []

        if not summary or not isinstance(summary, dict):
            return anomalies

        bias_metrics = summary.get("bias_metrics", {})
        depth_metrics = summary.get("depth_metrics", {})
        closure_metrics = summary.get("closure_metrics", {})
        repetition_metrics = summary.get("repetition_metrics", {})
        reflection_count = summary.get("reflection_count", 0)

        # Detect excessive stance bias
        stance_skew = bias_metrics.get("stance_skew", 0.0)
        if stance_skew > self.bias_threshold:
            anomalies.append(f"excessive_stance_bias:{stance_skew:.3f}")

        # Detect shallow reflection patterns
        shallow_ratio = depth_metrics.get("shallow_ratio", 0.0)
        if shallow_ratio > self.shallow_threshold:
            anomalies.append(f"shallow_reflection_pattern:{shallow_ratio:.3f}")

        # Detect low depth scores
        depth_score = depth_metrics.get("depth_score", 0.0)
        if depth_score < 0.3 and reflection_count >= 3:
            anomalies.append(f"low_depth_score:{depth_score:.3f}")

        # Detect poor commitment follow-through
        follow_through_ratio = closure_metrics.get("follow_through_ratio", 0.0)
        commitment_mentions = closure_metrics.get("commitment_mentions", 0)
        if commitment_mentions >= 3 and follow_through_ratio < 0.3:
            anomalies.append(f"poor_commitment_closure:{follow_through_ratio:.3f}")

        # Detect excessive repetition
        repetition_ratio = repetition_metrics.get("repetition_ratio", 0.0)
        if repetition_ratio > 0.8 and reflection_count >= 5:
            anomalies.append(f"excessive_repetition:{repetition_ratio:.3f}")

        # Detect lack of diversity
        diversity_score = repetition_metrics.get("diversity_score", 0.0)
        if diversity_score < 0.2 and reflection_count >= 5:
            anomalies.append(f"low_diversity:{diversity_score:.3f}")

        # Detect stagnation (no evolution indicators)
        evolution_indicators = closure_metrics.get("evolution_indicators", 0)
        if reflection_count >= 10 and evolution_indicators == 0:
            anomalies.append(f"reflection_stagnation:{reflection_count}")

        return anomalies

    def maybe_emit_report(
        self, eventlog, summary: Dict[str, Any], window: str
    ) -> Optional[str]:
        """
        Emit meta_reflection_report event with digest deduplication.
        Event shape:
          kind="meta_reflection_report"
          content="meta_analysis"
          meta={
            "component": "meta_reflection",
            "summary": summary,
            "anomalies": detected_anomalies,
            "window": window,
            "digest": <SHA256 over serialized summary + anomalies>,
            "deterministic": True,
            "bias_threshold": bias_threshold,
            "shallow_threshold": shallow_threshold
          }
        Returns event id or None if skipped due to idempotency.
        """
        # Detect anomalies before emission
        anomalies = self.detect_meta_anomalies(summary)

        # Generate deterministic digest
        digest_data = self._serialize_for_digest(summary, anomalies, window)
        digest = hashlib.sha256(digest_data.encode()).hexdigest()

        # Check for existing event with same digest (idempotency)
        all_events = eventlog.read_all()
        for event in all_events[-20:]:  # Check recent events for efficiency
            if (
                event.get("kind") == "meta_reflection_report"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None  # Skip - already exists

        # Prepare event metadata
        meta = {
            "component": "meta_reflection",
            "summary": summary,
            "anomalies": anomalies,
            "window": window,
            "digest": digest,
            "deterministic": True,
            "bias_threshold": self.bias_threshold,
            "shallow_threshold": self.shallow_threshold,
            "reflection_count": summary.get("reflection_count", 0),
        }

        # Emit the meta-reflection report event
        event_id = eventlog.append(
            kind="meta_reflection_report", content="meta_analysis", meta=meta
        )

        return event_id

    def _empty_summary(self) -> Dict[str, Any]:
        """Return empty summary structure."""
        return {
            "reflection_count": 0,
            "bias_metrics": {
                "positive_ratio": 0.0,
                "negative_ratio": 0.0,
                "neutral_ratio": 0.0,
                "stance_skew": 0.0,
            },
            "depth_metrics": {
                "avg_token_length": 0.0,
                "shallow_ratio": 0.0,
                "deep_ratio": 0.0,
                "depth_score": 0.0,
            },
            "closure_metrics": {
                "commitment_mentions": 0,
                "follow_through_ratio": 0.0,
                "evolution_indicators": 0,
            },
            "repetition_metrics": {
                "unique_themes": 0,
                "repetition_ratio": 0.0,
                "diversity_score": 0.0,
            },
        }

    def _analyze_bias_patterns(self, texts: List[str]) -> Dict[str, float]:
        """Analyze stance bias patterns in reflection texts."""
        stance_counts = {"positive": 0, "negative": 0, "neutral": 0}
        total_stances = 0

        for text in texts:
            normalized_text = self._normalize_text(text)
            words = set(normalized_text.split())

            # Count stance keywords
            for stance, keywords in self.STANCE_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in words:
                        stance_counts[stance] += 1
                        total_stances += 1

        if total_stances == 0:
            return {
                "positive_ratio": 0.0,
                "negative_ratio": 0.0,
                "neutral_ratio": 0.0,
                "stance_skew": 0.0,
            }

        # Calculate ratios
        positive_ratio = stance_counts["positive"] / total_stances
        negative_ratio = stance_counts["negative"] / total_stances
        neutral_ratio = stance_counts["neutral"] / total_stances

        # Calculate stance skew (deviation from balanced 0.33/0.33/0.33)
        balanced_ratio = 1.0 / 3.0
        skew = max(
            abs(positive_ratio - balanced_ratio),
            abs(negative_ratio - balanced_ratio),
            abs(neutral_ratio - balanced_ratio),
        )

        return {
            "positive_ratio": positive_ratio,
            "negative_ratio": negative_ratio,
            "neutral_ratio": neutral_ratio,
            "stance_skew": min(1.0, skew * 3.0),  # Normalize to [0.0, 1.0]
        }

    def _analyze_depth_patterns(self, texts: List[str]) -> Dict[str, float]:
        """Analyze depth patterns in reflection texts."""
        total_tokens = 0
        shallow_indicators = 0
        deep_indicators = 0

        for text in texts:
            normalized_text = self._normalize_text(text)
            words = normalized_text.split()
            total_tokens += len(words)

            word_set = set(words)

            # Count depth indicators
            for keyword in self.DEPTH_INDICATORS["shallow"]:
                if keyword in word_set:
                    shallow_indicators += 1

            for keyword in self.DEPTH_INDICATORS["deep"]:
                if keyword in word_set:
                    deep_indicators += 1

        text_count = len(texts)
        avg_token_length = total_tokens / text_count if text_count > 0 else 0.0

        total_indicators = shallow_indicators + deep_indicators
        if total_indicators == 0:
            shallow_ratio = 0.0
            deep_ratio = 0.0
        else:
            shallow_ratio = shallow_indicators / total_indicators
            deep_ratio = deep_indicators / total_indicators

        # Calculate composite depth score (token length + deep indicators - shallow indicators)
        # Normalize avg_token_length to [0.0, 1.0] assuming 100 tokens = 1.0
        normalized_length = min(1.0, avg_token_length / 100.0)
        depth_score = max(
            0.0, min(1.0, (normalized_length + deep_ratio - shallow_ratio) / 2.0)
        )

        return {
            "avg_token_length": avg_token_length,
            "shallow_ratio": shallow_ratio,
            "deep_ratio": deep_ratio,
            "depth_score": depth_score,
        }

    def _analyze_closure_patterns(
        self, reflection_texts: List[str], all_events: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Analyze commitment closure and evolution patterns."""
        commitment_mentions = 0
        follow_through_count = 0
        evolution_indicators = 0

        # Keywords that indicate commitment follow-through
        follow_through_keywords = [
            "completed",
            "finished",
            "accomplished",
            "achieved",
            "done",
            "fulfilled",
            "succeeded",
            "delivered",
            "resolved",
            "closed",
            "concluded",
        ]

        # Keywords that indicate evolution/learning
        evolution_keywords = [
            "learned",
            "discovered",
            "realized",
            "understood",
            "evolved",
            "grew",
            "improved",
            "adapted",
            "changed",
            "transformed",
            "developed",
            "progressed",
        ]

        # Extract commitment events for context
        commitment_events = []
        for event in all_events:
            if isinstance(event, dict) and event.get("kind") in [
                "commitment_open",
                "commitment_close",
            ]:
                commitment_events.append(event)

        for text in reflection_texts:
            normalized_text = self._normalize_text(text)
            words = set(normalized_text.split())

            # Check for commitment mentions (references to "commit", "goal", "promise", etc.)
            commitment_refs = [
                "commit",
                "goal",
                "promise",
                "pledge",
                "intention",
                "plan",
                "target",
            ]
            if any(ref in words for ref in commitment_refs):
                commitment_mentions += 1

                # Check for follow-through indicators
                if any(keyword in words for keyword in follow_through_keywords):
                    follow_through_count += 1

            # Check for evolution indicators
            if any(keyword in words for keyword in evolution_keywords):
                evolution_indicators += 1

        follow_through_ratio = (
            follow_through_count / commitment_mentions
            if commitment_mentions > 0
            else 0.0
        )

        return {
            "commitment_mentions": commitment_mentions,
            "follow_through_ratio": follow_through_ratio,
            "evolution_indicators": evolution_indicators,
        }

    def _analyze_repetition_patterns(self, texts: List[str]) -> Dict[str, float]:
        """Analyze repetition and diversity patterns in reflection texts."""
        if not texts:
            return {"unique_themes": 0, "repetition_ratio": 0.0, "diversity_score": 0.0}

        # Extract themes (significant words, excluding common words)
        stop_words = {
            "i",
            "me",
            "my",
            "myself",
            "we",
            "our",
            "ours",
            "ourselves",
            "you",
            "your",
            "yours",
            "he",
            "him",
            "his",
            "she",
            "her",
            "hers",
            "it",
            "its",
            "they",
            "them",
            "their",
            "what",
            "which",
            "who",
            "whom",
            "this",
            "that",
            "these",
            "those",
            "am",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "should",
            "could",
            "can",
            "may",
            "might",
            "must",
            "shall",
            "a",
            "an",
            "the",
            "and",
            "but",
            "if",
            "or",
            "because",
            "as",
            "until",
            "while",
            "of",
            "at",
            "by",
            "for",
            "with",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "up",
            "down",
            "in",
            "out",
            "on",
            "off",
            "over",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "any",
            "both",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "now",
        }

        all_themes = []
        theme_counts = Counter()

        for text in texts:
            normalized_text = self._normalize_text(text)
            words = [
                w for w in normalized_text.split() if len(w) > 3 and w not in stop_words
            ]

            # Extract 2-grams and 3-grams as themes
            themes = set()
            for i in range(len(words)):
                # Single significant words
                themes.add(words[i])

                # 2-grams
                if i < len(words) - 1:
                    themes.add(f"{words[i]}_{words[i+1]}")

                # 3-grams
                if i < len(words) - 2:
                    themes.add(f"{words[i]}_{words[i+1]}_{words[i+2]}")

            all_themes.extend(themes)
            for theme in themes:
                theme_counts[theme] += 1

        unique_themes = len(set(all_themes))
        total_themes = len(all_themes)

        if total_themes == 0:
            return {"unique_themes": 0, "repetition_ratio": 0.0, "diversity_score": 0.0}

        # Calculate repetition ratio (how much content is repeated)
        repeated_themes = sum(1 for count in theme_counts.values() if count > 1)
        repetition_ratio = repeated_themes / unique_themes if unique_themes > 0 else 0.0

        # Calculate diversity score (Shannon entropy-like measure)
        if unique_themes <= 1 or len(texts) == 1:
            diversity_score = 0.0  # Single text or single theme has no diversity
        else:
            # Normalize by log of unique themes for [0.0, 1.0] range
            import math

            entropy = -sum(
                (count / total_themes) * math.log(count / total_themes)
                for count in theme_counts.values()
            )
            max_entropy = math.log(unique_themes)
            diversity_score = entropy / max_entropy if max_entropy > 0 else 0.0

            # Penalize high repetition
            if repetition_ratio > 0.7:
                diversity_score = diversity_score * (1.0 - repetition_ratio)

        return {
            "unique_themes": unique_themes,
            "repetition_ratio": repetition_ratio,
            "diversity_score": diversity_score,
        }

    def _normalize_text(self, text: str) -> str:
        """Normalize text for consistent analysis."""
        if not isinstance(text, str):
            return ""

        # Convert to lowercase
        normalized = text.lower()

        # Remove punctuation and extra whitespace
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    def _serialize_for_digest(
        self, summary: Dict[str, Any], anomalies: List[str], window: str
    ) -> str:
        """Serialize summary, anomalies, and window deterministically for digest generation."""
        parts = []

        # Add window identifier
        parts.append(f"window:{window}")

        # Add reflection count
        parts.append(f"reflection_count:{summary.get('reflection_count', 0)}")

        # Add bias metrics in sorted order
        bias_metrics = summary.get("bias_metrics", {})
        for key in sorted(bias_metrics.keys()):
            value = bias_metrics[key]
            parts.append(f"bias_{key}:{value:.6f}")

        # Add depth metrics in sorted order
        depth_metrics = summary.get("depth_metrics", {})
        for key in sorted(depth_metrics.keys()):
            value = depth_metrics[key]
            parts.append(f"depth_{key}:{value:.6f}")

        # Add closure metrics in sorted order
        closure_metrics = summary.get("closure_metrics", {})
        for key in sorted(closure_metrics.keys()):
            value = closure_metrics[key]
            if isinstance(value, (int, float)):
                parts.append(f"closure_{key}:{value:.6f}")
            else:
                parts.append(f"closure_{key}:{value}")

        # Add repetition metrics in sorted order
        repetition_metrics = summary.get("repetition_metrics", {})
        for key in sorted(repetition_metrics.keys()):
            value = repetition_metrics[key]
            if isinstance(value, (int, float)):
                parts.append(f"repetition_{key}:{value:.6f}")
            else:
                parts.append(f"repetition_{key}:{value}")

        # Add anomalies in sorted order
        for anomaly in sorted(anomalies):
            parts.append(f"anomaly:{anomaly}")

        # Add configuration
        parts.append(f"bias_threshold:{self.bias_threshold:.6f}")
        parts.append(f"shallow_threshold:{self.shallow_threshold:.6f}")

        return "|".join(parts)
