"""Stage-aware behavioral adaptation for PMM runtime policies.

Provides deterministic, stage-specific parameter adaptation with explicit
ledger emission on stage transitions. All functions are pure and side-effect free.
"""

from __future__ import annotations
from typing import Literal


StageName = Literal["S0", "S1", "S2", "S3", "S4"]


class StageBehaviorManager:
    """
    Deterministic, stage-aware adapters for runtime policies.
    Pure functions + explicit ledger emission on stage change.
    """

    # Fixed policy table - reflection frequency multiplier bands (lo, hi) per stage
    REFLECTION_FREQ_BANDS = {
        "S0": (0.90, 1.10),
        "S1": (0.80, 1.15),
        "S2": (0.70, 1.20),
        "S3": (0.60, 1.30),
        "S4": (0.50, 1.40),
    }

    # Fixed policy table - commitment TTL multipliers per stage
    COMMITMENT_TTL_MULTIPLIERS = {
        "S0": 1.10,
        "S1": 1.00,
        "S2": 0.90,
        "S3": 0.80,
        "S4": 0.70,
    }

    def adapt_reflection_frequency(
        self, base_freq: float, stage: StageName, confidence: float
    ) -> float:
        """
        Returns a deterministic multiplier applied to base reflection frequency.
        - Monotone rules per stage (S0..S4), clamped to [0.25, 2.0].
        - Confidence ∈ [0,1] scales *within* each stage's band but never crosses stage bands.
        - No RNG; pure function.

        Args:
            base_freq: Base reflection frequency
            stage: Current stage ("S0" through "S4")
            confidence: Confidence value in [0, 1]

        Returns:
            Adapted frequency multiplier, clamped to [0.25, 2.0]
        """
        # Get stage band
        lo, hi = self.REFLECTION_FREQ_BANDS[stage]

        # Clamp confidence to [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        # Linear interpolation within band
        multiplier = lo + (hi - lo) * confidence

        # Clamp to global bounds
        return max(0.25, min(2.0, multiplier))

    def adapt_commitment_ttl(self, base_ttl_hours: float, stage: StageName) -> float:
        """
        Returns a deterministic TTL multiplier per stage, clamped to [0.5, 2.0].
        Pure function.

        Args:
            base_ttl_hours: Base TTL in hours
            stage: Current stage ("S0" through "S4")

        Returns:
            Adapted TTL in hours, clamped to [0.5, 2.0] times base
        """
        multiplier = self.COMMITMENT_TTL_MULTIPLIERS[stage]

        # Clamp multiplier to bounds
        clamped_multiplier = max(0.5, min(2.0, multiplier))

        return base_ttl_hours * clamped_multiplier

    def maybe_emit_stage_policy_update(
        self, eventlog, prev_stage: StageName, new_stage: StageName, confidence: float
    ) -> None:
        """
        Emits exactly one policy_update per *distinct* stage transition.
        Idempotent for the same (prev_stage, new_stage) pair.

        Args:
            eventlog: EventLog instance to append to
            prev_stage: Previous stage
            new_stage: New stage
            confidence: Confidence value for the transition
        """
        # No emission when stage unchanged
        if prev_stage == new_stage:
            return

        # Check for idempotency - avoid duplicate emissions for same transition
        if self._already_emitted_transition(eventlog, prev_stage, new_stage):
            return

        # Get policy parameters for new stage
        lo, hi = self.REFLECTION_FREQ_BANDS[new_stage]
        ttl_mult = self.COMMITMENT_TTL_MULTIPLIERS[new_stage]

        # Prepare metadata
        meta = {
            "component": "stage_behavior",
            "transition": {"from": prev_stage, "to": new_stage},
            "params": {
                "reflection_freq_band": [lo, hi],
                "ttl_mult": ttl_mult,
                "confidence": confidence,
            },
            "deterministic": True,
        }

        # Emit policy_update event
        eventlog.append(
            kind="policy_update", content="stage behavior policy", meta=meta
        )

    def _already_emitted_transition(
        self, eventlog, prev_stage: StageName, new_stage: StageName
    ) -> bool:
        """
        Check if transition has already been emitted to avoid duplicates.

        Args:
            eventlog: EventLog instance
            prev_stage: Previous stage
            new_stage: New stage

        Returns:
            True if transition already emitted, False otherwise
        """
        # Query existing policy_update events for stage_behavior component
        all_events = eventlog.read_all()
        for event in all_events:
            if (
                event.get("kind") == "policy_update"
                and event.get("meta", {}).get("component") == "stage_behavior"
            ):

                transition = event.get("meta", {}).get("transition", {})
                if (
                    transition.get("from") == prev_stage
                    and transition.get("to") == new_stage
                ):
                    return True
        return False
