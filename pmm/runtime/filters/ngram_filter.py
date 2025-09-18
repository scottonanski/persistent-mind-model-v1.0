"""N-gram Filter for PMM.

Deterministic filtering system that detects and flags undesirable repetition
in reflection text using n-gram analysis with full ledger integrity.
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional
import hashlib
import re
from collections import Counter


class NgramFilter:
    """
    Deterministic n-gram filter for detecting repetitive patterns in reflection text.
    Maintains full auditability through the event ledger.
    """

    def __init__(self, repeat_threshold: int = 3, ngram_lengths: List[int] = None):
        """Initialize n-gram filter.

        Args:
            repeat_threshold: Minimum count to flag n-gram as repeated
            ngram_lengths: List of n-gram lengths to analyze (default: [2, 3])
        """
        self.repeat_threshold = repeat_threshold
        self.ngram_lengths = ngram_lengths or [2, 3]

    def analyze_reflection_text(self, text: str) -> Dict[str, Any]:
        """
        Pure function.
        Extract n-grams (2-3 length, normalized) from reflection text.
        Returns analysis dict with n-gram counts and metadata.
        """
        if not text or not isinstance(text, str):
            return {
                "normalized_text": "",
                "total_tokens": 0,
                "ngrams": {},
                "ngram_counts": {},
                "analysis_metadata": {
                    "ngram_lengths": self.ngram_lengths,
                    "normalization": "lowercase_punctuation_stripped",
                },
            }

        # Normalize text: lowercase, remove punctuation, compact whitespace
        normalized = self._normalize_text(text)
        tokens = normalized.split()

        if len(tokens) == 0:
            return {
                "normalized_text": "",
                "total_tokens": 0,
                "ngrams": {},
                "ngram_counts": {},
                "analysis_metadata": {
                    "ngram_lengths": self.ngram_lengths,
                    "normalization": "lowercase_punctuation_stripped",
                },
            }

        # Extract n-grams for each specified length
        ngrams = {}
        ngram_counts = {}

        for n in self.ngram_lengths:
            if len(tokens) >= n:
                n_grams = []
                for i in range(len(tokens) - n + 1):
                    ngram = " ".join(tokens[i : i + n])
                    n_grams.append(ngram)

                ngrams[f"{n}gram"] = n_grams
                ngram_counts[f"{n}gram"] = dict(Counter(n_grams))

        return {
            "normalized_text": normalized,
            "total_tokens": len(tokens),
            "ngrams": ngrams,
            "ngram_counts": ngram_counts,
            "analysis_metadata": {
                "ngram_lengths": self.ngram_lengths,
                "normalization": "lowercase_punctuation_stripped",
            },
        }

    def detect_repeats(self, analysis: Dict[str, Any]) -> List[str]:
        """
        Pure function.
        Flag n-gram repeats above configurable threshold.
        Returns list of repeat flags (empty if none).
        """
        if not analysis or "ngram_counts" not in analysis:
            return []

        repeat_flags = []
        ngram_counts = analysis["ngram_counts"]

        for ngram_type, counts in ngram_counts.items():
            for ngram, count in counts.items():
                if count >= self.repeat_threshold:
                    repeat_flags.append(f"{ngram_type}_repeat:{count}:{ngram[:50]}")

        return repeat_flags

    def maybe_emit_filter_event(
        self, eventlog, src_event_id: str, analysis: Dict[str, Any], repeats: List[str]
    ) -> Optional[str]:
        """
        Emit ngram_filter_report event with digest deduplication.
        Event shape:
          kind="ngram_filter_report"
          content="analysis"
          meta={
            "component": "ngram_filter",
            "analysis": analysis,
            "repeats": repeats,
            "digest": <SHA256 over analysis + repeats>,
            "src_event_id": src_event_id,
            "deterministic": True,
            "threshold_used": repeat_threshold
          }
        Returns event id or None if skipped due to idempotency.
        """
        # Generate deterministic digest
        digest_data = self._serialize_for_digest(analysis, repeats)
        digest = hashlib.sha256(digest_data.encode()).hexdigest()

        # Check for existing event with same digest (idempotency)
        all_events = eventlog.read_all()
        for event in all_events[-20:]:  # Check recent events for efficiency
            if (
                event.get("kind") == "ngram_filter_report"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None  # Skip - already exists

        # Prepare event metadata
        meta = {
            "component": "ngram_filter",
            "analysis": analysis,
            "repeats": repeats,
            "digest": digest,
            "src_event_id": src_event_id,
            "deterministic": True,
            "threshold_used": self.repeat_threshold,
            "ngram_lengths": self.ngram_lengths,
            "total_tokens": analysis.get("total_tokens", 0),
        }

        # Emit the filter event
        event_id = eventlog.append(
            kind="ngram_filter_report", content="analysis", meta=meta
        )

        return event_id

    def _normalize_text(self, text: str) -> str:
        """Normalize text deterministically: lowercase, strip punctuation, compact whitespace."""
        # Convert to lowercase
        normalized = text.lower()

        # Remove punctuation (keep only alphanumeric and whitespace)
        normalized = re.sub(r"[^\w\s]", " ", normalized)

        # Compact whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    def _serialize_for_digest(
        self, analysis: Dict[str, Any], repeats: List[str]
    ) -> str:
        """Serialize analysis and repeats deterministically for digest generation."""
        parts = []

        # Add normalized text
        parts.append(f"text:{analysis.get('normalized_text', '')}")

        # Add token count
        parts.append(f"tokens:{analysis.get('total_tokens', 0)}")

        # Add n-gram counts in sorted order
        ngram_counts = analysis.get("ngram_counts", {})
        for ngram_type in sorted(ngram_counts.keys()):
            counts = ngram_counts[ngram_type]
            for ngram in sorted(counts.keys()):
                count = counts[ngram]
                parts.append(f"{ngram_type}:{ngram}:{count}")

        # Add repeats in sorted order
        for repeat in sorted(repeats):
            parts.append(f"repeat:{repeat}")

        # Add threshold
        parts.append(f"threshold:{self.repeat_threshold}")

        return "|".join(parts)
