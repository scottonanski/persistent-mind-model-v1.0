"""Adaptive reflection cadence engine for PMM.

Provides deterministic reflection decision-making based on recent behavioral patterns,
stage progression, and commitment state. All logic is pure and side-effect free.
"""

from __future__ import annotations

import math
from typing import Literal

StageName = Literal["S0", "S1", "S2", "S3", "S4"]


class AdaptiveReflectionCadence:
    """
    Pure, deterministic reflection gating using recent window stats.
    No imports from stage/trait modules; all params passed in.
    """

    # Stage multiplier tables
    STAGE_TURNS_MULT = {"S0": 1.0, "S1": 0.95, "S2": 0.90, "S3": 0.85, "S4": 0.80}

    STAGE_TIME_MULT = {"S0": 1.0, "S1": 0.95, "S2": 0.90, "S3": 0.85, "S4": 0.80}

    def should_reflect(
        self,
        *,
        turns_since_last: int,
        seconds_since_last: float,
        stage: StageName,
        confidence: float,
        base_min_turns: int,
        base_min_seconds: float,
        ias: list[float],
        gas: list[float],
        recent_kinds: list[str],
        open_commitments: int,
    ) -> tuple[bool, str]:
        """
        Returns (decision, reason_code) where reason_code ∈ {
          "time_gate","turn_gate","plateau_booster","low_diversity_booster",
          "commitment_pressure","stage_relax","ok"
        }.
        Deterministic rule-order; first satisfied booster/gate decides.
        """
        # Clamp confidence to [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        # Calculate stage-adjusted thresholds
        turns_mult = self._get_stage_multiplier(
            stage, confidence, self.STAGE_TURNS_MULT
        )
        time_mult = self._get_stage_multiplier(stage, confidence, self.STAGE_TIME_MULT)

        required_turns = math.ceil(base_min_turns * turns_mult)
        required_seconds = base_min_seconds * time_mult

        # Hard gates (must pass) - check in specified order
        if turns_since_last < required_turns:
            return (False, "turn_gate")

        if seconds_since_last < required_seconds:
            return (False, "time_gate")

        # Gates passed, check boosters

        # Plateau booster
        if self._is_plateau(ias, gas):
            return (True, "plateau_booster")

        # Low diversity booster
        if self._is_low_diversity(recent_kinds):
            return (True, "low_diversity_booster")

        # Commitment pressure
        if open_commitments >= 5:
            return (True, "commitment_pressure")

        # Stage relaxation for higher stages
        if stage in {"S3", "S4"}:
            return (True, "stage_relax")

        # Default
        return (True, "ok")

    def maybe_emit_decision(
        self, eventlog, ctx: dict, decision: tuple[bool, str]
    ) -> str | None:
        """
        Append exactly one event per unique ctx['tick_id'] if provided.
        If ctx lacks 'tick_id', emit unconditionally.
        Idempotent by (kind, content, meta.ctx.tick_id) when present.
        Returns event id or None if skipped.
        """
        tick_id = ctx.get("tick_id")

        # Check for idempotency if tick_id is provided
        if tick_id is not None and self._already_emitted_decision(eventlog, tick_id):
            return None

        # Prepare compact context (exclude large arrays, include lengths + last values)
        compact_ctx = self._compact_context(ctx)

        # Prepare metadata
        meta = {
            "deterministic": True,
            "decision": {"reflect": decision[0], "reason": decision[1]},
            "ctx": compact_ctx,
        }

        # Emit reflection_decision event
        event_id = eventlog.append(
            kind="reflection_decision", content="adaptive_cadence", meta=meta
        )

        return str(event_id)

    def _get_stage_multiplier(
        self, stage: StageName, confidence: float, mult_table: dict[str, float]
    ) -> float:
        """Calculate stage multiplier with confidence modulation."""
        base_mult = mult_table[stage]

        # Modulate by confidence within ±10%: mult *= (0.9 + 0.2*confidence)
        confidence_factor = 0.9 + 0.2 * confidence
        adjusted_mult = base_mult * confidence_factor

        # Clamp to [0.5, 2.0]
        return max(0.5, min(2.0, adjusted_mult))

    def _is_plateau(self, ias: list[float], gas: list[float]) -> bool:
        """Check if recent IAS/GAS values indicate a plateau."""
        if len(ias) < 5 or len(gas) < 5:
            return False

        # Check last 4 deltas for both IAS and GAS
        ias_deltas = [abs(ias[i] - ias[i - 1]) for i in range(-4, 0)]
        gas_deltas = [abs(gas[i] - gas[i - 1]) for i in range(-4, 0)]

        # All deltas must be < 0.01
        return all(delta < 0.01 for delta in ias_deltas + gas_deltas)

    def _is_low_diversity(self, recent_kinds: list[str]) -> bool:
        """Check if recent event kinds show low diversity."""
        if len(recent_kinds) < 10:
            return False

        # Take last 10 events
        tail_10 = recent_kinds[-10:]
        unique_kinds = len(set(tail_10))
        diversity_ratio = unique_kinds / len(tail_10)

        # Check diversity threshold
        if diversity_ratio > 0.4:
            return False

        # Check for longest same-kind run in tail 10
        max_run = self._calculate_max_run_length(tail_10)
        return max_run >= 4

    def _calculate_max_run_length(self, kinds: list[str]) -> int:
        """Calculate the longest streak of consecutive same-kind events."""
        if not kinds:
            return 0

        max_run = 1
        current_run = 1
        prev_kind = kinds[0]

        for kind in kinds[1:]:
            if kind == prev_kind:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                current_run = 1
                prev_kind = kind

        return max_run

    def _compact_context(self, ctx: dict) -> dict:
        """Create compact context excluding large arrays, including lengths + last values."""
        compact = {}

        # Copy scalar values directly
        for key, value in ctx.items():
            if not isinstance(value, list):
                compact[key] = value

        # Handle arrays with length + last value
        for key, value in ctx.items():
            if isinstance(value, list):
                compact[f"{key}_length"] = len(value)
                if value:  # Non-empty list
                    compact[f"{key}_last"] = value[-1]

        return compact

    def _already_emitted_decision(self, eventlog, tick_id: str) -> bool:
        """Check if decision has already been emitted for this tick_id."""
        # Query existing reflection_decision events
        all_events = eventlog.read_all()
        for event in all_events:
            if (
                event.get("kind") == "reflection_decision"
                and event.get("content") == "adaptive_cadence"
            ):

                event_ctx = event.get("meta", {}).get("ctx", {})
                if event_ctx.get("tick_id") == tick_id:
                    return True
        return False
