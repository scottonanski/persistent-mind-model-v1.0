"""Autonomy helpers extracted from loop.tick.

Pure helpers to keep `loop.py` smaller and easier to reason about.
Functions here must be deterministic and side-effect free.
"""

from __future__ import annotations

from collections.abc import Iterable


def compute_reflection_target_params(cadence: dict[str, object]) -> dict[str, object]:
    """Return normalized reflection cadence params dict.

    Expects keys: min_turns, min_time_s, force_reflect_if_stuck.
    Casts values to int/bool for stable equality checks.
    """
    return {
        "min_turns": int(cadence.get("min_turns", 0)),
        "min_time_s": int(cadence.get("min_time_s", 0)),
        "force_reflect_if_stuck": bool(cadence.get("force_reflect_if_stuck", False)),
    }


def compute_drift_params(mult: dict[str, float]) -> dict[str, object]:
    """Return normalized drift params structure for policy_update."""
    return {
        "mult": {
            "openness": float(mult.get("openness", 0.0)),
            "conscientiousness": float(mult.get("conscientiousness", 0.0)),
            "neuroticism": float(mult.get("neuroticism", 0.0)),
        }
    }


def policy_update_exists(
    events: Iterable[dict], *, component: str, stage: str, params: dict[str, object]
) -> bool:
    """Check whether an equivalent policy_update event already exists.

    Scans the event stream in reverse order for a matching component, stage,
    and params dict. Returns True if found.
    """
    # Avoid copying large event lists when possible
    try:
        iterator = reversed(events)  # type: ignore[arg-type]
    except TypeError:
        iterator = reversed(list(events))
    for ev in iterator:
        if ev.get("kind") != "policy_update":
            continue
        m = ev.get("meta") or {}
        if (
            str(m.get("component")) == str(component)
            and str(m.get("stage")) == str(stage)
            and dict(m.get("params") or {}) == dict(params)
        ):
            return True
    return False
