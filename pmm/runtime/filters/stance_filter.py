"""Stance Filter for PMM.

Deterministic filtering system that detects stance keywords/categories and
flags contradictory stance sequences in commitment text with full ledger integrity.
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional
import hashlib
import re
from collections import defaultdict


class StanceFilter:
    """
    Deterministic stance filter for detecting stance categories and contradictory
    sequences in commitment text. Maintains full auditability through the event ledger.
    """

    # Deterministic stance keyword mappings
    STANCE_CATEGORIES = {
        "obligation": {
            "strong": [
                "must",
                "shall",
                "required",
                "mandatory",
                "obligated",
                "compelled",
            ],
            "moderate": ["should", "ought", "expected", "supposed", "recommended"],
            "weak": ["could", "might", "may", "possibly", "potentially"],
        },
        "prohibition": {
            "strong": [
                "never",
                "forbidden",
                "prohibited",
                "banned",
                "cannot",
                "must not",
            ],
            "moderate": ["should not", "ought not", "discouraged", "avoid", "refrain"],
            "weak": ["prefer not", "rather not", "hesitant", "unlikely"],
        },
        "commitment": {
            "strong": ["will", "commit", "promise", "guarantee", "ensure", "pledge"],
            "moderate": ["intend", "plan", "aim", "strive", "endeavor", "work toward"],
            "weak": ["hope", "try", "attempt", "consider", "explore", "look into"],
        },
        "capability": {
            "strong": ["can", "able", "capable", "skilled", "proficient", "expert"],
            "moderate": ["competent", "adequate", "sufficient", "reasonable", "decent"],
            "weak": ["learning", "developing", "improving", "practicing", "studying"],
        },
    }

    # Contradictory stance pairs (category, intensity) -> (category, intensity)
    CONTRADICTORY_PAIRS = [
        (("obligation", "strong"), ("prohibition", "strong")),
        (("obligation", "strong"), ("prohibition", "moderate")),
        (("commitment", "strong"), ("prohibition", "strong")),
        (("commitment", "strong"), ("prohibition", "moderate")),
        (("capability", "strong"), ("prohibition", "strong")),
    ]

    def __init__(self, shift_window: int = 5):
        """Initialize stance filter.

        Args:
            shift_window: Number of recent commitments to analyze for shifts
        """
        self.shift_window = shift_window

    def analyze_commitment_text(self, text: str) -> Dict[str, Any]:
        """
        Pure function.
        Detect stance keywords/categories using deterministic dictionary mapping.
        Returns analysis dict with detected stances and metadata.
        """
        if not text or not isinstance(text, str):
            return {
                "normalized_text": "",
                "detected_stances": {},
                "stance_summary": {},
                "analysis_metadata": {
                    "categories_checked": list(self.STANCE_CATEGORIES.keys()),
                    "normalization": "lowercase_word_boundary",
                },
            }

        # Normalize text for analysis
        normalized = self._normalize_text(text)

        # Detect stances by category and intensity
        detected_stances = defaultdict(lambda: defaultdict(list))
        stance_summary = defaultdict(int)

        for category, intensities in self.STANCE_CATEGORIES.items():
            for intensity, keywords in intensities.items():
                for keyword in keywords:
                    # Use word boundary matching to avoid partial matches
                    pattern = r"\b" + re.escape(keyword) + r"\b"
                    matches = re.findall(pattern, normalized, re.IGNORECASE)
                    if matches:
                        detected_stances[category][intensity].extend(matches)
                        stance_summary[f"{category}_{intensity}"] += len(matches)

        # Convert defaultdict to regular dict for serialization
        detected_stances_dict = {}
        for category, intensities in detected_stances.items():
            detected_stances_dict[category] = dict(intensities)

        return {
            "normalized_text": normalized,
            "detected_stances": detected_stances_dict,
            "stance_summary": dict(stance_summary),
            "analysis_metadata": {
                "categories_checked": list(self.STANCE_CATEGORIES.keys()),
                "normalization": "lowercase_word_boundary",
            },
        }

    def detect_shifts(self, commitment_history: List[Dict[str, Any]]) -> List[str]:
        """
        Pure function.
        Flag contradictory stance sequences (e.g., "must" → "never") in recent commitments.
        Returns list of shift flags (empty if none).

        Args:
            commitment_history: List of commitment analysis dicts from analyze_commitment_text()
        """
        if not commitment_history or len(commitment_history) < 2:
            return []

        shift_flags = []

        # Analyze recent window of commitments
        recent_commitments = commitment_history[-self.shift_window :]

        # Extract stance patterns from each commitment
        stance_patterns = []
        for i, analysis in enumerate(recent_commitments):
            patterns = []
            stance_summary = analysis.get("stance_summary", {})

            for stance_key, count in stance_summary.items():
                if count > 0:
                    category, intensity = stance_key.rsplit("_", 1)
                    patterns.append((category, intensity, count))

            if patterns:
                stance_patterns.append((i, patterns))

        # Check for contradictory sequences
        for i in range(len(stance_patterns) - 1):
            current_idx, current_patterns = stance_patterns[i]
            next_idx, next_patterns = stance_patterns[i + 1]

            for curr_category, curr_intensity, curr_count in current_patterns:
                for next_category, next_intensity, next_count in next_patterns:
                    # Check if this pair is contradictory
                    curr_stance = (curr_category, curr_intensity)
                    next_stance = (next_category, next_intensity)

                    if self._is_contradictory_pair(curr_stance, next_stance):
                        shift_flags.append(
                            f"stance_shift:{curr_category}_{curr_intensity}->{next_category}_{next_intensity}:positions_{current_idx}_{next_idx}"
                        )

        return shift_flags

    def maybe_emit_filter_event(
        self, eventlog, src_event_id: str, analysis: Dict[str, Any], shifts: List[str]
    ) -> Optional[str]:
        """
        Emit stance_filter_report event with digest deduplication.
        Event shape:
          kind="stance_filter_report"
          content="analysis"
          meta={
            "component": "stance_filter",
            "analysis": analysis,
            "shifts": shifts,
            "digest": <SHA256 over analysis + shifts>,
            "src_event_id": src_event_id,
            "deterministic": True,
            "shift_window": shift_window
          }
        Returns event id or None if skipped due to idempotency.
        """
        # Generate deterministic digest
        digest_data = self._serialize_for_digest(analysis, shifts)
        digest = hashlib.sha256(digest_data.encode()).hexdigest()

        # Check for existing event with same digest (idempotency)
        all_events = eventlog.read_all()
        for event in all_events[-20:]:  # Check recent events for efficiency
            if (
                event.get("kind") == "stance_filter_report"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None  # Skip - already exists

        # Prepare event metadata
        meta = {
            "component": "stance_filter",
            "analysis": analysis,
            "shifts": shifts,
            "digest": digest,
            "src_event_id": src_event_id,
            "deterministic": True,
            "shift_window": self.shift_window,
            "categories_analyzed": list(self.STANCE_CATEGORIES.keys()),
            "stance_count": len(analysis.get("stance_summary", {})),
        }

        # Emit the filter event
        event_id = eventlog.append(
            kind="stance_filter_report", content="analysis", meta=meta
        )

        return event_id

    def _normalize_text(self, text: str) -> str:
        """Normalize text for stance analysis: lowercase, preserve word boundaries."""
        # Convert to lowercase but preserve punctuation for word boundary detection
        normalized = text.lower().strip()

        # Compact multiple whitespace but preserve single spaces
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized

    def _is_contradictory_pair(self, stance1: tuple, stance2: tuple) -> bool:
        """Check if two stance tuples (category, intensity) are contradictory."""
        # Check direct contradictions
        if (stance1, stance2) in self.CONTRADICTORY_PAIRS:
            return True
        if (stance2, stance1) in self.CONTRADICTORY_PAIRS:
            return True

        # Check same category with opposing intensities
        category1, intensity1 = stance1
        category2, intensity2 = stance2

        if category1 == category2:
            # Strong -> weak in same category can indicate inconsistency
            if (intensity1 == "strong" and intensity2 == "weak") or (
                intensity1 == "weak" and intensity2 == "strong"
            ):
                return True

        return False

    def _serialize_for_digest(self, analysis: Dict[str, Any], shifts: List[str]) -> str:
        """Serialize analysis and shifts deterministically for digest generation."""
        parts = []

        # Add normalized text
        parts.append(f"text:{analysis.get('normalized_text', '')}")

        # Add stance summary in sorted order
        stance_summary = analysis.get("stance_summary", {})
        for stance_key in sorted(stance_summary.keys()):
            count = stance_summary[stance_key]
            parts.append(f"stance:{stance_key}:{count}")

        # Add detected stances in sorted order
        detected_stances = analysis.get("detected_stances", {})
        for category in sorted(detected_stances.keys()):
            intensities = detected_stances[category]
            for intensity in sorted(intensities.keys()):
                keywords = intensities[intensity]
                for keyword in sorted(keywords):
                    parts.append(f"detected:{category}_{intensity}:{keyword}")

        # Add shifts in sorted order
        for shift in sorted(shifts):
            parts.append(f"shift:{shift}")

        # Add window size
        parts.append(f"window:{self.shift_window}")

        return "|".join(parts)
