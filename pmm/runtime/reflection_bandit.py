from __future__ import annotations

import random as _random

from pmm.runtime.loop import io as _io
from pmm.runtime.metrics import compute_ias_gas

# Fixed arms and templates (names only used for logging; prompt integration optional)
ARMS: tuple[str, ...] = (
    "succinct",
    "question_form",
    "narrative",
    "checklist",
    "analytical",
)

# Bidirectional label mappings to prevent drift between bandit arms and prompt templates
# Bandit uses "question_form", templates use "question" internally
PROMPT_LABEL_TO_ARM: dict[str, str] = {
    "succinct": "succinct",
    "question": "question_form",  # Legacy template label -> bandit arm
    "narrative": "narrative",
    "checklist": "checklist",
    "analytical": "analytical",
}

ARM_TO_PROMPT_LABEL: dict[str, str] = {
    "succinct": "succinct",
    "question_form": "question",  # Bandit arm -> template label
    "narrative": "narrative",
    "checklist": "checklist",
    "analytical": "analytical",
}

_EPSILON = 0.10
_rng = _random.Random(42)  # deterministic RNG

# Small deterministic clamp for guidance bias influence (per-arm cap)
EPS_BIAS: float = 0.03

# Structured mapping from guidance type -> arm label
ARM_FROM_GUIDANCE_TYPE: dict[str, str] = {
    "checklist": "checklist",
    "succinct": "succinct",
    "narrative": "narrative",
    "question": "question_form",
    "analytical": "analytical",
}


def _current_tick(events: list[dict]) -> int:
    return 1 + sum(1 for ev in events if ev.get("kind") == "autonomy_tick")


def _arm_rewards(
    events: list[dict], stage: str | None = None
) -> dict[str, list[float]]:
    """Aggregate rewards by arm, optionally filtered by stage context.

    Args:
        events: Event log entries
        stage: If provided, only include rewards from this stage (e.g., "S0", "S1")

    Returns:
        Dict mapping arm names to lists of reward values
    """
    scores: dict[str, list[float]] = {a: [] for a in ARMS}
    for ev in events:
        if ev.get("kind") != "bandit_reward":
            continue
        m = ev.get("meta") or {}

        # Filter by stage if provided (context-aware aggregation)
        if stage is not None:
            ev_stage = m.get("stage")
            if ev_stage != stage:
                continue

        arm = str(m.get("arm") or "")

        # Normalize legacy "question" label to "question_form"
        if arm == "question":
            arm = "question_form"

        try:
            r = float(m.get("reward") or 0.0)
        except Exception:
            r = 0.0
        if arm in scores:
            scores[arm].append(r)
    return scores


def _best_arm_by_mean(rew: dict[str, list[float]]) -> str:
    best = None
    best_mean = -1.0
    for arm in ARMS:
        vals = rew.get(arm) or []
        mean = sum(vals) / len(vals) if vals else 0.0
        if mean > best_mean:
            best = arm
            best_mean = mean
    return best or ARMS[0]


def choose_arm(events: list[dict], stage: str | None = None) -> tuple[str, int]:
    """
    Deterministic epsilon-greedy arm selection with optional context filtering.

    Args:
        events: Event log entries
        stage: If provided, uses stage-specific reward history for exploitation

    Returns:
        (arm, tick) tuple
    """
    tick = _current_tick(events)
    # exploration
    if _rng.random() < _EPSILON:
        arm = ARMS[_rng.randrange(len(ARMS))]
        return (arm, tick)
    # exploitation - use context-aware rewards if stage provided
    rewards = _arm_rewards(events, stage=stage)
    arm = _best_arm_by_mean(rewards)
    return (arm, tick)


# ---------------- Directive-guided bias (deterministic, bounded) ----------------


def _arm_means_from_rewards(rew: dict[str, list[float]]) -> dict[str, float]:
    means: dict[str, float] = {}
    for arm in ARMS:
        vals = rew.get(arm) or []
        means[arm] = (sum(vals) / len(vals)) if vals else 0.0
    return means


def apply_guidance_bias(
    arm_means: dict[str, float], guidance_items: list[dict], eps_bias: float = EPS_BIAS
) -> tuple[dict[str, float], dict[str, float]]:
    """Apply a small, clamped bias to arm means using only structured fields.

    Inputs: guidance_items = [{"type": str, "score": float}, ...]
    For each item, map type -> arm via ARM_FROM_GUIDANCE_TYPE and add score*eps_bias
    to that arm's delta. Clamp each arm's cumulative delta in [-eps_bias, eps_bias].

    Returns (biased_means, delta_by_arm).
    Missing/unknown type or score -> ignored.
    """
    delta: dict[str, float] = {a: 0.0 for a in ARMS}
    for it in guidance_items or []:
        arm = ARM_FROM_GUIDANCE_TYPE.get(str(it.get("type") or ""))
        if not arm:
            continue
        try:
            s = float(it.get("score"))
        except Exception:
            continue
        if s <= 0.0:
            continue
        new_d = float(delta.get(arm, 0.0)) + s * float(eps_bias)
        # clamp per-arm to ±eps_bias
        delta[arm] = max(-float(eps_bias), min(float(eps_bias), new_d))

    biased: dict[str, float] = {
        a: float(arm_means.get(a, 0.0)) + float(delta[a]) for a in ARMS
    }
    return biased, delta


def _best_arm_from_means(means: dict[str, float]) -> str:
    best = None
    best_v = -1.0
    for arm in ARMS:
        v = float(means.get(arm, 0.0))
        if v > best_v:
            best = arm
            best_v = v
    return best or ARMS[0]


def choose_arm_biased(
    arm_means: dict[str, float],
    guidance_items: list[dict],
    *,
    eps_bias: float = EPS_BIAS,
) -> tuple[str, dict[str, float]]:
    """Deterministic selection using biased means (no exploration in this helper).

    Returns (arm, delta_by_arm).
    """
    biased_means, delta = apply_guidance_bias(
        arm_means, guidance_items, eps_bias=eps_bias
    )
    arm = _best_arm_from_means(biased_means)
    return arm, delta


# Reward computation helpers


def _ias_at_tick(events: list[dict], tick_no: int) -> float:
    # Find latest reflection up to that tick and extract IAS embedded in meta.telemetry
    # If none, compute on the fly from events up to that point
    # First, find the event id of the given autonomy tick
    tick_ids = [
        int(ev.get("id") or 0) for ev in events if ev.get("kind") == "autonomy_tick"
    ]
    target_id = None
    if tick_no <= 0:
        tick_no = 1
    if len(tick_ids) >= tick_no:
        target_id = tick_ids[tick_no - 1]
    if target_id is not None:
        subset = [e for e in events if int(e.get("id") or 0) <= target_id]
    else:
        subset = events
    ias, _gas = compute_ias_gas(subset)
    return float(ias)


def _count_between_ticks(
    events: list[dict], kind: str, start_tick: int, end_tick: int
) -> int:
    # Determine id ranges
    tick_ids = [
        int(ev.get("id") or 0) for ev in events if ev.get("kind") == "autonomy_tick"
    ]
    if not tick_ids:
        return 0

    def _tick_to_id(t: int) -> int | None:
        if t <= 0:
            return None
        if t > len(tick_ids):
            return tick_ids[-1]
        return tick_ids[t - 1]

    start_id = _tick_to_id(start_tick) or 0
    end_id = _tick_to_id(end_tick) or tick_ids[-1]
    cnt = 0
    for ev in events:
        eid = int(ev.get("id") or 0)
        if eid <= start_id:
            continue
        if eid > end_id:
            break
        if ev.get("kind") == kind:
            cnt += 1
    return cnt


def compute_reward(
    events: list[dict], *, horizon: int = 3
) -> tuple[float, str | None, int | None]:
    """Return (reward, arm, chosen_tick) or (0.0, None, None) if insufficient context.
    Reward = 0.5 * max(0, ΔIAS) + 0.5 * close_ratio, clipped [0,1].
    """
    # last chosen
    chosen = None
    for ev in reversed(events):
        if ev.get("kind") == "bandit_arm_chosen":
            chosen = ev
            break
    if not chosen:
        return (0.0, None, None)
    m = chosen.get("meta") or {}
    arm = str(m.get("arm") or "")
    try:
        tick_chosen = int(m.get("tick") or 0)
    except Exception:
        tick_chosen = 0
    if tick_chosen <= 0:
        return (0.0, arm or None, None)
    ias_before = _ias_at_tick(events, tick_chosen)
    ias_after = _ias_at_tick(events, tick_chosen + horizon)
    delta_ias = max(0.0, float(ias_after) - float(ias_before))
    closes = _count_between_ticks(
        events, "commitment_close", tick_chosen, tick_chosen + horizon
    )
    opens = _count_between_ticks(
        events, "commitment_open", tick_chosen, tick_chosen + horizon
    )
    close_ratio = (closes / max(1, opens)) if opens >= 0 else 0.0
    raw = 0.5 * delta_ias + 0.5 * close_ratio
    if raw < 0.0:
        raw = 0.0
    if raw > 1.0:
        raw = 1.0
    return (float(raw), arm or None, tick_chosen)


def maybe_log_reward(eventlog, *, horizon: int = 3) -> int | None:
    """If sufficient ticks have passed since the last bandit_arm_chosen, append bandit_reward.
    Returns new event id or None if not emitted.
    """
    events = eventlog.read_all()
    # Current tick
    tick_now = _current_tick(events)
    # Build FIFO of chosen arms with ticks and mark rewards to find the oldest unmatched choice
    chosen_queue: list[tuple[str, int, str | None]] = []  # (arm, tick, stage)
    rewarded_counts: list[str] = []
    for ev in events:
        k = ev.get("kind")
        if k == "bandit_arm_chosen":
            m = ev.get("meta") or {}
            arm = str(m.get("arm") or "")
            try:
                t = int(m.get("tick") or 0)
            except Exception:
                t = 0
            # Extract stage context from choice event
            stage = (
                (m.get("extra") or {}).get("stage")
                if isinstance(m.get("extra"), dict)
                else None
            )
            chosen_queue.append((arm, t, stage))
        elif k == "bandit_reward":
            m = ev.get("meta") or {}
            arm = str(m.get("arm") or "")
            rewarded_counts.append(arm)
    # Pop off matched choices one-by-one by arm occurrence order
    unmatched: tuple[str, int, str | None] | None = None
    arm_match_progress: dict[str, int] = {}
    for arm, t, stage in chosen_queue:
        count_used = arm_match_progress.get(arm, 0)
        if rewarded_counts.count(arm) > count_used:
            arm_match_progress[arm] = count_used + 1
            continue  # matched
        unmatched = (arm, t, stage)
        break
    if not unmatched:
        return None
    arm_u, tick_chosen, stage_chosen = unmatched
    if tick_chosen <= 0 or (tick_now - tick_chosen) < horizon:
        return None
    reward, arm_calc, _ = compute_reward(events, horizon=horizon)
    arm_final = arm_calc or arm_u

    # Infer current stage if not captured at choice time
    if stage_chosen is None:
        try:
            from pmm.runtime.stage_tracker import StageTracker

            stage_chosen, _ = StageTracker.infer_stage(events)
        except Exception:
            stage_chosen = None

    # Append reward with stage context for future filtering
    return _io.append_bandit_reward(
        eventlog,
        component="reflection",
        arm=arm_final,
        reward=reward,
        extra={"stage": stage_chosen} if stage_chosen else None,
    )


# Removed duplicate emit_reflection() - use pmm.runtime.loop.reflection.emit_reflection() instead
