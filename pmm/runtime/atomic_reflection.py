"""Atomic Reflection System for PMM.

Implements fine-grained, deterministic reflection that breaks reflection into
atomic sub-steps: analyze → propose → commit.

Each sub-step is ledger-replayable, idempotent, and auditable.
"""

from __future__ import annotations
from typing import List, Dict, Any
import hashlib
import json
from collections import defaultdict


class AtomicReflection:
    """
    Deterministic fine-grained reflection system.
    Breaks a reflection into atomic sub-steps (analyze → propose → commit).
    """

    def __init__(self, window_size: int = 100):
        self.window_size = window_size

    def analyze(self, events: List[Dict]) -> Dict[str, Any]:
        """
        Pure function. Analyze recent events, extract deterministic signals:
          - commitment stats (open/close counts, streaks)
          - trait deltas (OCEAN drift averages)
          - novelty/plateau indicators (from diversity & emergence)
        Returns structured dict of analysis.
        """
        # Use sliding window of recent events
        window = (
            events[-self.window_size :] if len(events) > self.window_size else events
        )

        if not window:
            return {
                "commitment_stats": {
                    "opens": 0,
                    "closes": 0,
                    "close_rate": 0.0,
                    "streak": 0,
                },
                "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
                "novelty_indicators": {
                    "reflection_diversity": 0.0,
                    "emergence_score": 0.0,
                },
                "event_count": 0,
                "window_size": self.window_size,
            }

        # Analyze commitment patterns
        commitment_stats = self._analyze_commitments(window)

        # Analyze trait drift patterns
        trait_deltas = self._analyze_trait_deltas(window)

        # Analyze novelty and emergence patterns
        novelty_indicators = self._analyze_novelty_patterns(window)

        return {
            "commitment_stats": commitment_stats,
            "trait_deltas": trait_deltas,
            "novelty_indicators": novelty_indicators,
            "event_count": len(window),
            "window_size": self.window_size,
            "events": window,  # Store events for proposal logic
        }

    def propose(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pure function. Deterministically propose changes based on analysis:
          - open/close commitments
          - adjust reflection cadence
          - recommend trait reinforcement
        Returns dict of proposals. No ledger writes here.
        """
        proposals = {
            "commitment_actions": [],
            "cadence_adjustments": [],
            "trait_reinforcements": [],
            "policy_updates": [],
        }

        # Extract analysis components
        commitment_stats = analysis.get("commitment_stats", {})
        trait_deltas = analysis.get("trait_deltas", {})
        novelty_indicators = analysis.get("novelty_indicators", {})

        # Propose commitment actions based on close rate
        close_rate = commitment_stats.get("close_rate", 0.0)
        opens = commitment_stats.get("opens", 0)

        # Only propose actions if there's actual commitment activity
        if opens > 0 and close_rate < 0.3:  # Low completion rate
            proposals["commitment_actions"].append(
                {
                    "action": "reduce_commitment_load",
                    "reason": f"Low close rate ({close_rate:.2f}) indicates overcommitment",
                    "priority": "high",
                }
            )
        elif close_rate > 0.8:  # High completion rate
            proposals["commitment_actions"].append(
                {
                    "action": "increase_commitment_ambition",
                    "reason": f"High close rate ({close_rate:.2f}) suggests capacity for more",
                    "priority": "medium",
                }
            )

        # Propose cadence adjustments based on novelty (only if there are reflections)
        reflection_diversity = novelty_indicators.get("reflection_diversity", 0.0)

        # Check if there are actual reflections to base decisions on
        has_reflections = any(
            e.get("kind") == "reflection" for e in analysis.get("events", [])
        )

        if has_reflections and reflection_diversity < 0.3:  # Low diversity
            proposals["cadence_adjustments"].append(
                {
                    "action": "increase_reflection_frequency",
                    "reason": f"Low reflection diversity ({reflection_diversity:.2f}) needs more frequent reflection",
                    "adjustment": {"min_turns": -1, "min_time_s": -10},
                }
            )
        elif reflection_diversity > 0.7:  # High diversity
            proposals["cadence_adjustments"].append(
                {
                    "action": "decrease_reflection_frequency",
                    "reason": f"High reflection diversity ({reflection_diversity:.2f}) allows less frequent reflection",
                    "adjustment": {"min_turns": 1, "min_time_s": 10},
                }
            )

        # Propose trait reinforcements for significant drifts
        for trait, delta in trait_deltas.items():
            abs_delta = abs(delta)
            if abs_delta > 0.1:  # Significant drift threshold
                direction = "increase" if delta > 0 else "decrease"
                proposals["trait_reinforcements"].append(
                    {
                        "trait": trait,
                        "action": f"reinforce_{direction}",
                        "delta": delta,
                        "reason": f"Significant {trait} drift ({delta:+.3f}) needs reinforcement",
                    }
                )

        # Propose policy updates based on emergence patterns
        emergence_score = novelty_indicators.get("emergence_score", 0.0)
        if emergence_score < 0.2:  # Low emergence
            proposals["policy_updates"].append(
                {
                    "component": "novelty_threshold",
                    "action": "decrease_threshold",
                    "value": 0.05,
                    "reason": f"Low emergence score ({emergence_score:.2f}) needs lower novelty threshold",
                }
            )
        elif emergence_score > 0.8:  # High emergence
            proposals["policy_updates"].append(
                {
                    "component": "novelty_threshold",
                    "action": "increase_threshold",
                    "value": 0.05,
                    "reason": f"High emergence score ({emergence_score:.2f}) allows higher novelty threshold",
                }
            )

        return proposals

    def commit(
        self, eventlog, proposals: Dict[str, Any], src_event_id: str
    ) -> List[str]:
        """
        Append atomic reflection events:
          kind="atomic_reflection_step"
          content ∈ {"analyze","propose","commit"}
          meta includes full input/output
        Enforce idempotency: (src_event_id, content) unique in ledger.
        Returns list of event ids appended.
        """
        appended_ids = []

        # Check existing events for idempotency
        try:
            existing_events = eventlog.read_all()
            existing_steps = set()
            for event in existing_events:
                if (
                    event.get("kind") == "atomic_reflection_step"
                    and (event.get("meta") or {}).get("src_event_id") == src_event_id
                ):
                    step = event.get("content", "")
                    existing_steps.add(step)
        except Exception:
            existing_steps = set()

        # Commit analyze step
        if "analyze" not in existing_steps:
            analyze_meta = {
                "component": "atomic_reflection",
                "step": "analyze",
                "src_event_id": src_event_id,
                "deterministic": True,
                "window_size": self.window_size,
            }
            try:
                event_id = eventlog.append(
                    "atomic_reflection_step", "analyze", analyze_meta
                )
                if event_id:
                    appended_ids.append(event_id)
            except Exception:
                pass

        # Commit propose step
        if "propose" not in existing_steps:
            # Create deterministic digest of proposals
            proposals_json = json.dumps(proposals, sort_keys=True)
            digest = hashlib.sha256(proposals_json.encode()).hexdigest()[:16]

            propose_meta = {
                "component": "atomic_reflection",
                "step": "propose",
                "src_event_id": src_event_id,
                "deterministic": True,
                "proposals": proposals,
                "digest": digest,
            }
            try:
                event_id = eventlog.append(
                    "atomic_reflection_step", "propose", propose_meta
                )
                if event_id:
                    appended_ids.append(event_id)
            except Exception:
                pass

        # Commit commit step (meta-commit)
        if "commit" not in existing_steps:
            commit_meta = {
                "component": "atomic_reflection",
                "step": "commit",
                "src_event_id": src_event_id,
                "deterministic": True,
                "appended_count": len(appended_ids),
            }
            try:
                event_id = eventlog.append(
                    "atomic_reflection_step", "commit", commit_meta
                )
                if event_id:
                    appended_ids.append(event_id)
            except Exception:
                pass

        return appended_ids

    def _analyze_commitments(self, events: List[Dict]) -> Dict[str, Any]:
        """Analyze commitment patterns in event window."""
        opens = sum(1 for e in events if e.get("kind") == "commitment_open")
        closes = sum(1 for e in events if e.get("kind") == "commitment_close")

        close_rate = (closes / opens) if opens > 0 else 0.0

        # Calculate streak (consecutive closes without opens)
        streak = 0
        for event in reversed(events):
            if event.get("kind") == "commitment_close":
                streak += 1
            elif event.get("kind") == "commitment_open":
                break

        return {
            "opens": opens,
            "closes": closes,
            "close_rate": close_rate,
            "streak": streak,
        }

    def _analyze_trait_deltas(self, events: List[Dict]) -> Dict[str, float]:
        """Analyze trait drift patterns in event window."""
        trait_updates = []

        for event in events:
            if event.get("kind") == "trait_update":
                meta = event.get("meta", {})
                changes = meta.get("changes", {})
                if changes:
                    trait_updates.append(changes)

        # Calculate average deltas for each trait
        trait_deltas = {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0}
        trait_names = {
            "openness": "O",
            "conscientiousness": "C",
            "extraversion": "E",
            "agreeableness": "A",
            "neuroticism": "N",
        }

        if trait_updates:
            trait_sums = defaultdict(float)
            trait_counts = defaultdict(int)

            for update in trait_updates:
                for full_name, delta in update.items():
                    short_name = trait_names.get(full_name)
                    if short_name:
                        trait_sums[short_name] += float(delta)
                        trait_counts[short_name] += 1

            for trait in trait_deltas:
                if trait_counts[trait] > 0:
                    trait_deltas[trait] = trait_sums[trait] / trait_counts[trait]

        return trait_deltas

    def _analyze_novelty_patterns(self, events: List[Dict]) -> Dict[str, float]:
        """Analyze novelty and emergence patterns in event window."""
        # Calculate reflection diversity
        reflection_texts = []
        for event in events:
            if event.get("kind") == "reflection":
                text = event.get("content", "")
                if text:
                    reflection_texts.append(text.lower())

        reflection_diversity = 0.0
        if reflection_texts:
            all_words = []
            for text in reflection_texts:
                words = text.split()
                all_words.extend(words)

            if all_words:
                unique_words = set(all_words)
                reflection_diversity = len(unique_words) / len(all_words)

        # Extract emergence score from recent emergence reports
        emergence_score = 0.0
        for event in reversed(events):
            if event.get("kind") == "emergence_report":
                meta = event.get("meta", {})
                metrics = meta.get("metrics", {})
                emergence_score = float(metrics.get("composite_score", 0.0))
                break

        return {
            "reflection_diversity": min(1.0, reflection_diversity * 2.0),
            "emergence_score": emergence_score,
        }

    def run_full_cycle(
        self, eventlog, events: List[Dict], src_event_id: str
    ) -> Dict[str, Any]:
        """
        Run complete analyze → propose → commit cycle.
        Returns dict with analysis, proposals, and committed event IDs.
        """
        # Step 1: Analyze
        analysis = self.analyze(events)

        # Step 2: Propose
        proposals = self.propose(analysis)

        # Step 3: Commit
        committed_ids = self.commit(eventlog, proposals, src_event_id)

        return {
            "analysis": analysis,
            "proposals": proposals,
            "committed_event_ids": committed_ids,
            "src_event_id": src_event_id,
        }
