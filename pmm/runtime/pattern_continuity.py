"""Pattern Continuity System for PMM.

Deterministic system for recognizing repeated patterns of commitments,
phrasing, and behaviors across sessions. Must be fully reconstructable
from the ledger, idempotent, and reproducible.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Any

from pmm.utils.parsers import tokenize_alphanumeric


class PatternContinuity:
    """
    Deterministic system for recognizing repeated patterns of commitments,
    phrasing, and behaviors across sessions.
    """

    def __init__(self, window_size: int = 100):
        """Initialize pattern continuity analyzer.

        Args:
            window_size: Number of recent events to analyze for patterns
        """
        self.window_size = window_size

    def analyze_patterns(self, events: list[dict]) -> dict[str, Any]:
        """
        Pure function.
        Analyze recent events for continuity signals:
          - commitment_open/close repetition rates
          - repeated reflection phrasing (ngram frequency)
          - recurrence of stage transitions
        Returns dict summary with counts, ratios, and top repeats.
        """
        # Use sliding window of recent events
        window = (
            events[-self.window_size :] if len(events) > self.window_size else events
        )

        # Analyze commitment patterns
        commitment_patterns = self._analyze_commitment_patterns(window)

        # Analyze reflection phrasing patterns
        reflection_patterns = self._analyze_reflection_patterns(window)

        # Analyze stage transition patterns
        stage_patterns = self._analyze_stage_patterns(window)

        # Generate summary
        summary = {
            "commitment_patterns": commitment_patterns,
            "reflection_patterns": reflection_patterns,
            "stage_patterns": stage_patterns,
            "window_size": len(window),
            "total_events": len(events),
        }

        return summary

    def _analyze_commitment_patterns(self, events: list[dict]) -> dict[str, Any]:
        """Analyze commitment open/close repetition patterns."""
        commitment_texts = {}  # cid -> text
        commitment_opens = defaultdict(list)  # text -> [event_ids]
        commitment_closes = defaultdict(list)  # text -> [event_ids]

        for event in events:
            kind = event.get("kind", "")
            meta = event.get("meta", {})
            event_id = event.get("id")

            if kind == "commitment_open":
                cid = meta.get("cid")
                text = meta.get("text", "").strip().lower()
                if cid and text:
                    commitment_texts[cid] = text
                    commitment_opens[text].append(event_id)

            elif kind == "commitment_close":
                cid = meta.get("cid")
                if cid and cid in commitment_texts:
                    text = commitment_texts[cid]
                    commitment_closes[text].append(event_id)

        # Calculate repetition statistics
        repeated_opens = {
            text: len(opens)
            for text, opens in commitment_opens.items()
            if len(opens) > 1
        }
        repeated_closes = {
            text: len(closes)
            for text, closes in commitment_closes.items()
            if len(closes) > 1
        }

        # Calculate open/close ratios
        ratios = {}
        for text in commitment_opens:
            opens = len(commitment_opens[text])
            closes = len(commitment_closes.get(text, []))
            ratios[text] = {
                "opens": opens,
                "closes": closes,
                "ratio": closes / opens if opens > 0 else 0.0,
            }

        return {
            "total_unique_commitments": len(commitment_opens),
            "repeated_opens": repeated_opens,
            "repeated_closes": repeated_closes,
            "open_close_ratios": ratios,
            "top_repeated_opens": dict(
                sorted(repeated_opens.items(), key=lambda x: x[1], reverse=True)[:5]
            ),
        }

    def _analyze_reflection_patterns(self, events: list[dict]) -> dict[str, Any]:
        """Analyze repeated reflection phrasing using n-gram frequency."""
        reflection_texts = []

        for event in events:
            if event.get("kind") == "reflection":
                content = event.get("content", "").strip()
                if content:
                    reflection_texts.append(content)

        if not reflection_texts:
            return {
                "total_reflections": 0,
                "unique_ngrams": 0,
                "repeated_ngrams": {},
                "top_repeated_ngrams": {},
            }

        # Extract n-grams (2-grams and 3-grams)
        ngram_counts = Counter()

        for text in reflection_texts:
            # Normalize text: lowercase, tokenize alphanumerically
            words = tokenize_alphanumeric(text)

            # Generate 2-grams and 3-grams
            for n in [2, 3]:
                for i in range(len(words) - n + 1):
                    ngram = " ".join(words[i : i + n])
                    if len(ngram.strip()) > 0:
                        ngram_counts[ngram] += 1

        # Find repeated n-grams (appearing more than once)
        repeated_ngrams = {
            ngram: count for ngram, count in ngram_counts.items() if count > 1
        }

        return {
            "total_reflections": len(reflection_texts),
            "unique_ngrams": len(ngram_counts),
            "repeated_ngrams": repeated_ngrams,
            "top_repeated_ngrams": dict(
                sorted(repeated_ngrams.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
        }

    def _analyze_stage_patterns(self, events: list[dict]) -> dict[str, Any]:
        """Analyze stage transition recurrence patterns."""
        stage_transitions = []
        current_stage = None

        for event in events:
            if event.get("kind") == "stage_update":
                new_stage = event.get("meta", {}).get("stage")
                if new_stage and new_stage != current_stage:
                    if current_stage is not None:
                        stage_transitions.append((current_stage, new_stage))
                    current_stage = new_stage

        if not stage_transitions:
            return {
                "total_transitions": 0,
                "unique_transitions": 0,
                "repeated_transitions": {},
                "oscillation_sequences": [],
            }

        # Count transition frequencies
        transition_counts = Counter(stage_transitions)
        repeated_transitions = {
            trans: count for trans, count in transition_counts.items() if count > 1
        }

        # Detect oscillation sequences (A->B->A->B pattern)
        oscillation_sequences = []
        if len(stage_transitions) >= 3:
            for i in range(len(stage_transitions) - 2):
                seq = stage_transitions[i : i + 3]
                # Check for A->B->A pattern
                if (
                    seq[0][1] == seq[1][0]
                    and seq[1][1] == seq[2][0]
                    and seq[0][0] == seq[2][1]
                ):
                    oscillation_sequences.append(seq)

        return {
            "total_transitions": len(stage_transitions),
            "unique_transitions": len(transition_counts),
            "repeated_transitions": repeated_transitions,
            "oscillation_sequences": oscillation_sequences,
            "transition_sequence": stage_transitions[-10:],  # Last 10 transitions
        }

    def detect_loops(self, patterns: dict[str, Any]) -> list[str]:
        """
        Pure function.
        Identify problematic continuity patterns:
          - >3 identical commitments reopened in last N events
          - >5 identical reflection n-grams in last N reflections
          - stage oscillation (e.g. S1→S2→S1→S2 in last N)
        Returns list of loop/anomaly labels (empty if none).
        """
        anomalies = []

        # Check commitment repetition loops
        commitment_patterns = patterns.get("commitment_patterns", {})
        repeated_opens = commitment_patterns.get("repeated_opens", {})

        for text, count in repeated_opens.items():
            if count > 3:
                anomalies.append(f"commitment_loop:{count}:{text[:50]}")

        # Check reflection n-gram repetition
        reflection_patterns = patterns.get("reflection_patterns", {})
        repeated_ngrams = reflection_patterns.get("repeated_ngrams", {})

        for ngram, count in repeated_ngrams.items():
            if count > 5:
                anomalies.append(f"reflection_loop:{count}:{ngram[:50]}")

        # Check stage oscillation patterns
        stage_patterns = patterns.get("stage_patterns", {})
        oscillation_sequences = stage_patterns.get("oscillation_sequences", [])

        if len(oscillation_sequences) > 0:
            for seq in oscillation_sequences:
                seq_str = "->".join([f"{a}->{b}" for a, b in seq])
                anomalies.append(f"stage_oscillation:{seq_str}")

        # Check for excessive stage transitions (thrashing)
        repeated_transitions = stage_patterns.get("repeated_transitions", {})
        for (from_stage, to_stage), count in repeated_transitions.items():
            if count > 3:
                anomalies.append(f"stage_thrashing:{count}:{from_stage}->{to_stage}")

        return anomalies

    def maybe_emit_report(
        self, eventlog, src_event_id: str, summary: dict[str, Any]
    ) -> str | None:
        """
        Emit a pattern_continuity_report event with:
          kind="pattern_continuity_report"
          content="analysis"
          meta={
            "component": "pattern_continuity",
            "summary": summary,
            "digest": <SHA256 over summary>,
            "src_event_id": src_event_id,
            "deterministic": True
          }
        Idempotent: skip if digest already exists.
        Returns event id or None if skipped.
        """
        # Generate deterministic digest of summary
        summary_str = self._serialize_summary_for_digest(summary)
        digest = hashlib.sha256(summary_str.encode()).hexdigest()

        # Check for existing event with same digest (idempotency)
        all_events = eventlog.read_all()
        for event in all_events[-20:]:  # Check recent events for efficiency
            if (
                event.get("kind") == "pattern_continuity_report"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None  # Skip - already exists

        # Prepare event metadata
        meta = {
            "component": "pattern_continuity",
            "summary": summary,
            "digest": digest,
            "src_event_id": src_event_id,
            "deterministic": True,
            "window_size": summary.get("window_size", 0),
            "total_events": summary.get("total_events", 0),
        }

        # Emit the report event
        event_id = eventlog.append(
            kind="pattern_continuity_report", content="analysis", meta=meta
        )

        return event_id

    def _serialize_summary_for_digest(self, summary: dict[str, Any]) -> str:
        """Serialize summary deterministically for digest generation."""
        # Create a deterministic string representation
        parts = []

        # Commitment patterns
        cp = summary.get("commitment_patterns", {})
        parts.append(f"commitments:{cp.get('total_unique_commitments', 0)}")

        # Sort repeated opens for deterministic ordering
        repeated_opens = cp.get("repeated_opens", {})
        for text in sorted(repeated_opens.keys()):
            parts.append(f"open_repeat:{text}:{repeated_opens[text]}")

        # Reflection patterns
        rp = summary.get("reflection_patterns", {})
        parts.append(f"reflections:{rp.get('total_reflections', 0)}")

        # Sort repeated n-grams for deterministic ordering
        repeated_ngrams = rp.get("repeated_ngrams", {})
        for ngram in sorted(repeated_ngrams.keys()):
            parts.append(f"ngram_repeat:{ngram}:{repeated_ngrams[ngram]}")

        # Stage patterns
        sp = summary.get("stage_patterns", {})
        parts.append(f"stages:{sp.get('total_transitions', 0)}")

        # Sort repeated transitions for deterministic ordering
        repeated_transitions = sp.get("repeated_transitions", {})
        for from_stage, to_stage in sorted(repeated_transitions.keys()):
            count = repeated_transitions[(from_stage, to_stage)]
            parts.append(f"stage_repeat:{from_stage}->{to_stage}:{count}")

        # Window metadata
        parts.append(f"window:{summary.get('window_size', 0)}")
        parts.append(f"total:{summary.get('total_events', 0)}")

        return "|".join(parts)
