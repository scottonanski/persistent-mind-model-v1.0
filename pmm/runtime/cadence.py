from __future__ import annotations

from dataclasses import dataclass

# ---- constants (no env flags) ----
MIN_TURNS_BETWEEN_REFLECTIONS = 2  # require N assistant replies between reflections
MIN_SECONDS_BETWEEN_REFLECTIONS = 10.0  # wall clock guard (if ts is present)
NOVELTY_EPS = 0.05  # minimal delta in GAS to qualify as "novel"


@dataclass(frozen=True)
class CadenceState:
    last_reflect_ts: float | None
    turns_since_reflect: int
    last_gas: float
    current_gas: float


def _enough_turns(turns_since_reflect: int) -> bool:
    return int(turns_since_reflect) >= int(MIN_TURNS_BETWEEN_REFLECTIONS)


def _enough_seconds(now_ts: float | None, last_ts: float | None) -> bool:
    if now_ts is None or last_ts is None:
        return True  # if no timestamps, don't block
    try:
        return (float(now_ts) - float(last_ts)) >= float(
            MIN_SECONDS_BETWEEN_REFLECTIONS
        )
    except Exception:
        return True


def _has_novelty(prev: float, cur: float) -> bool:
    try:
        return (float(cur) - float(prev)) >= float(NOVELTY_EPS)
    except Exception:
        return False


def should_reflect(state: CadenceState, *, now_ts: float | None) -> bool:
    """
    Deterministic gating:
      - require min turns AND min seconds; OR
      - allow if novelty is present
    Never blocks chat; caller uses result to decide reflect() or skip.
    """
    turns_ok = _enough_turns(state.turns_since_reflect)
    time_ok = _enough_seconds(now_ts, state.last_reflect_ts)
    novelty = _has_novelty(state.last_gas, state.current_gas)
    # policy: reflect if (turns_ok and time_ok) OR novelty
    return (turns_ok and time_ok) or novelty
