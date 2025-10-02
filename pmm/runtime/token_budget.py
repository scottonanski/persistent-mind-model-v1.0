# pmm/runtime/token_budget.py
from __future__ import annotations

from dataclasses import dataclass

from .capability_resolver import CapabilityResolver, ModelCaps

# ---------- Policy ----------
_POLICY_ID = "alloc.v1.0"

# Task bands (min, max) for single completion;
# allocator will clamp against provider hint and remaining budget.
_BANDS: dict[str, tuple[int, int]] = {
    "chat": (256, 2048),
    "reflect_single": (512, 2048),
    "reflect_recursive": (512, 2048),
    "report": (1024, 4096),
    "tool_explain": (256, 768),
}


# ---------- Types ----------
@dataclass(frozen=True)
class Allocation:
    target_out: int
    safety_reserve: int
    tool_reserve: int
    remain_after_reserve: int
    policy_id: str
    notes: str = ""


# ---------- Helpers ----------
def _clamp(x: int, lo: int, hi: int) -> int:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


# ---------- API ----------
def allocate_completion_budget(
    *,
    resolver: CapabilityResolver,
    model_key: str,
    prompt_tokens: int,
    task: str,
    tooling_on: bool,
    first_pass: bool = True,
    tuner_scale: float = 1.0,
) -> Allocation:
    """
    Deterministic, task-aware token allocator.
    - Reserves headroom (safety + tool).
    - Picks a target completion size as a fraction of remaining budget.
    - Clamps to task band and provider-discovered hint.
    Invariants: truth-first, monotonic, reproducible via policy_id.
    """
    caps: ModelCaps = resolver.ensure_caps(model_key)

    # Reserves (conservative & monotonic)
    safety = max(512, int(0.05 * caps.max_ctx))
    tool_r = 512 if tooling_on else 256

    remain = max(0, caps.max_ctx - prompt_tokens - safety - tool_r)

    lo, hi = _BANDS.get(task, (256, caps.max_out_hint))

    # First pass of deep reflections gets a bit more room; continuations shrink later.
    frac = 0.60 if (task.startswith("reflect") and first_pass) else 0.50
    target = int(frac * remain)

    # Apply tuner scale (bounded implicitly by clamping below)
    if tuner_scale and tuner_scale != 1.0:
        try:
            target = int(target * float(tuner_scale))
        except Exception:
            pass

    # Clamp within task band and provider hint, and ensure non-negative
    target = _clamp(target, lo, min(hi, caps.max_out_hint))
    if target < 0:
        target = 0

    return Allocation(
        target_out=target,
        safety_reserve=safety,
        tool_reserve=tool_r,
        remain_after_reserve=remain,
        policy_id=_POLICY_ID,
        notes=f"caps={caps.source}:{caps.max_ctx}/{caps.max_out_hint}",
    )


def next_continuation_target(prev_target: int) -> int:
    """
    Geometric decay for continuations to guarantee convergence and cost control.
    """
    return max(256, int(prev_target * 0.75))
