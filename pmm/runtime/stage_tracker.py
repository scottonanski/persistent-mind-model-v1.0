from __future__ import annotations

from enum import IntEnum

N_WINDOW = 10
HYST = 0.03

# Stage bucket thresholds (lower bounds, inclusive) as (IAS_min, GAS_min)
STAGES = {
    "S0": (None, None),  # special: IAS < 0.35 or GAS < 0.20
    "S1": (0.35, 0.20),
    "S2": (0.50, 0.35),
    "S3": (0.70, 0.55),
    "S4": (0.85, 0.75),
}


class StageLevel(IntEnum):
    S0 = 0
    S1 = 1
    S2 = 2
    S3 = 3
    S4 = 4
    UNKNOWN = -1


_STR_TO_LEVEL: dict[str, StageLevel] = {
    "S0": StageLevel.S0,
    "S1": StageLevel.S1,
    "S2": StageLevel.S2,
    "S3": StageLevel.S3,
    "S4": StageLevel.S4,
}


def stage_str_to_level(stage_str: str | None) -> int:
    """Map 'S0'..'S4' to 0..4; anything else => -1. Safe for None inputs."""
    if not stage_str:
        return int(StageLevel.UNKNOWN)
    return int(_STR_TO_LEVEL.get(stage_str.strip().upper(), StageLevel.UNKNOWN))


def stage_level_to_str(level: int) -> str:
    """Map 0..4 back to 'S#'; UNKNOWN/-1 => 'S?'. For display only."""
    for k, v in _STR_TO_LEVEL.items():
        if int(v) == int(level):
            return k
    return "S?"


# Stage-aware policy hints (static, deterministic). Values are component -> params dict.
# These are consumed by the runtime loop to emit policy_update events on stage transitions.
POLICY_HINTS_BY_STAGE = {
    "S0": {"reflection_style": {"arm": "succinct"}, "recall": {"recall_budget": 1}},
    "S1": {
        "reflection_style": {"arm": "question_form"},
        "recall": {"recall_budget": 2},
    },
    "S2": {"reflection_style": {"arm": "analytical"}, "recall": {"recall_budget": 3}},
    "S3": {"reflection_style": {"arm": "narrative"}, "recall": {"recall_budget": 3}},
    "S4": {"reflection_style": {"arm": "checklist"}, "recall": {"recall_budget": 3}},
}


def policy_arm_for_stage(stage: str | None) -> str | None:
    """Return the reflection_style arm for a given stage, or None if not found.

    Centralizes stage → arm lookup with normalization. Returns bandit-compatible
    arm names (e.g., 'question_form' not 'question').

    Args:
        stage: Stage string (e.g., 'S0', 'S1', ..., 'S4')

    Returns:
        Arm name string (e.g., 'succinct', 'question_form') or None
    """
    if not stage:
        return None
    try:
        hints = POLICY_HINTS_BY_STAGE.get(str(stage).strip())
        if not hints:
            return None
        style_params = hints.get("reflection_style")
        if not isinstance(style_params, dict):
            return None
        arm = str(style_params.get("arm") or "").strip()
        return arm if arm else None
    except Exception:
        return None


def _telemetry_from_event(ev: dict) -> tuple[float, float] | None:
    if ev.get("kind") == "autonomy_tick":
        tel = (ev.get("meta") or {}).get("telemetry") or {}
        if "IAS" in tel and "GAS" in tel:
            return float(tel["IAS"]), float(tel["GAS"])
    if ev.get("kind") == "reflection":
        tel = (ev.get("meta") or {}).get("telemetry") or {}
        if "IAS" in tel and "GAS" in tel:
            return float(tel["IAS"]), float(tel["GAS"])
    return None


def _mean(nums: list[float]) -> float:
    return sum(nums) / float(len(nums)) if nums else 0.0


def _bucket(ias: float, gas: float) -> str:
    # S4 top bucket
    if ias >= 0.85 and gas >= 0.75:
        return "S4"
    # S3
    if ias >= 0.70 and gas >= 0.55:
        return "S3"
    # S2
    if ias >= 0.50 and gas >= 0.35:
        return "S2"
    # S1: Either identity formation OR goal achievement
    if ias >= 0.35 or gas >= 0.20:
        return "S1"
    # S0 (stalled): both ias < 0.35 AND gas < 0.20
    return "S0"


class StageTracker:
    @staticmethod
    def infer_stage(events: list[dict]) -> tuple[str, dict[str, float]]:
        # Prefer autonomy_tick telemetry; if less than N, fill with reflection telemetry
        autos: list[tuple[float, float]] = []
        refls: list[tuple[float, float]] = []
        for ev in events:
            t = _telemetry_from_event(ev)
            if not t:
                continue
            if ev.get("kind") == "autonomy_tick":
                autos.append(t)
            elif ev.get("kind") == "reflection":
                refls.append(t)
        # Take last N from autos, then fill from refls tail if needed
        autos_tail = autos[-N_WINDOW:]
        needed = max(0, N_WINDOW - len(autos_tail))
        refl_tail = refls[-needed:] if needed > 0 else []
        window = autos_tail + refl_tail
        iases = [x for x, _ in window]
        gases = [y for _, y in window]
        ias_mean = _mean(iases)
        gas_mean = _mean(gases)
        stage = _bucket(ias_mean, gas_mean)
        snapshot = {
            "IAS_mean": float(ias_mean),
            "GAS_mean": float(gas_mean),
            "count": int(len(window)),
            "window": int(N_WINDOW),
        }
        return stage, snapshot

    @staticmethod
    def _bounds(stage: str) -> tuple[float | None, float | None]:
        return STAGES.get(stage, (None, None))

    @classmethod
    def with_hysteresis(
        cls,
        prev_stage: str | None,
        next_stage: str,
        snapshot: dict[str, float],
        events: list[dict],
    ) -> bool:
        count = int(snapshot.get("count", 0))
        if count < 3:
            return False
        if not prev_stage:
            return True
        if prev_stage == next_stage:
            return False
        ias = float(snapshot.get("IAS_mean", 0.0))
        gas = float(snapshot.get("GAS_mean", 0.0))

        # Determine direction
        # Define stage order for comparison
        order = ["S0", "S1", "S2", "S3", "S4"]
        try:
            prev_idx = order.index(prev_stage)
            next_idx = order.index(next_stage)
        except ValueError:
            return True

        if next_idx > prev_idx:
            # Upward: must exceed next stage lower bounds by +HYST
            low_ias, low_gas = cls._bounds(next_stage)
            low_ias = low_ias if low_ias is not None else 0.0
            low_gas = low_gas if low_gas is not None else 0.0
            return (ias >= (low_ias + HYST)) and (gas >= (low_gas + HYST))
        else:
            # Downward: must undershoot current stage lower bounds by -HYST
            low_ias, low_gas = cls._bounds(prev_stage)
            if prev_stage == "S0":
                # S0 special: move further down only if significantly below S0 thresholds
                return (ias < (0.35 - HYST)) or (gas < (0.20 - HYST))
            low_ias = low_ias if low_ias is not None else 0.0
            low_gas = low_gas if low_gas is not None else 0.0
            return (ias < (low_ias - HYST)) or (gas < (low_gas - HYST))
