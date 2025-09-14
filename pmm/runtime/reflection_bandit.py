from __future__ import annotations

from typing import List, Dict, Tuple, Optional
import random as _random
from pmm.runtime.metrics import compute_ias_gas

# Fixed arms and templates (names only used for logging; prompt integration optional)
ARMS: Tuple[str, ...] = (
    "succinct",
    "question_form",
    "narrative",
    "checklist",
    "analytical",
)

_EPSILON = 0.10
_rng = _random.Random(42)  # deterministic RNG

# Small deterministic clamp for guidance bias influence (per-arm cap)
EPS_BIAS: float = 0.03

# Structured mapping from guidance type -> arm label
ARM_FROM_GUIDANCE_TYPE: Dict[str, str] = {
    "checklist": "checklist",
    "succinct": "succinct",
    "narrative": "narrative",
    "question": "question_form",
    "analytical": "analytical",
}


def _current_tick(events: List[Dict]) -> int:
    return 1 + sum(1 for ev in events if ev.get("kind") == "autonomy_tick")


def _arm_rewards(events: List[Dict]) -> Dict[str, List[float]]:
    scores: Dict[str, List[float]] = {a: [] for a in ARMS}
    for ev in events:
        if ev.get("kind") != "bandit_reward":
            continue
        m = ev.get("meta") or {}
        arm = str(m.get("arm") or "")
        try:
            r = float(m.get("reward") or 0.0)
        except Exception:
            r = 0.0
        if arm in scores:
            scores[arm].append(r)
    return scores


def _best_arm_by_mean(rew: Dict[str, List[float]]) -> str:
    best = None
    best_mean = -1.0
    for arm in ARMS:
        vals = rew.get(arm) or []
        mean = sum(vals) / len(vals) if vals else 0.0
        if mean > best_mean:
            best = arm
            best_mean = mean
    return best or ARMS[0]


def choose_arm(events: List[Dict]) -> Tuple[str, int]:
    """
    Deterministic epsilon-greedy arm selection.
    Returns (arm, tick).
    """
    tick = _current_tick(events)
    # exploration
    if _rng.random() < _EPSILON:
        arm = ARMS[_rng.randrange(len(ARMS))]
        return (arm, tick)
    # exploitation
    rewards = _arm_rewards(events)
    arm = _best_arm_by_mean(rewards)
    return (arm, tick)


# ---------------- Directive-guided bias (deterministic, bounded) ----------------


def _arm_means_from_rewards(rew: Dict[str, List[float]]) -> Dict[str, float]:
    means: Dict[str, float] = {}
    for arm in ARMS:
        vals = rew.get(arm) or []
        means[arm] = (sum(vals) / len(vals)) if vals else 0.0
    return means


def apply_guidance_bias(
    arm_means: Dict[str, float], guidance_items: List[Dict], eps_bias: float = EPS_BIAS
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Apply a small, clamped bias to arm means using only structured fields.

    Inputs: guidance_items = [{"type": str, "score": float}, ...]
    For each item, map type -> arm via ARM_FROM_GUIDANCE_TYPE and add score*eps_bias
    to that arm's delta. Clamp each arm's cumulative delta in [-eps_bias, eps_bias].

    Returns (biased_means, delta_by_arm).
    Missing/unknown type or score -> ignored.
    """
    delta: Dict[str, float] = {a: 0.0 for a in ARMS}
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

    biased: Dict[str, float] = {
        a: float(arm_means.get(a, 0.0)) + float(delta[a]) for a in ARMS
    }
    return biased, delta


def _best_arm_from_means(means: Dict[str, float]) -> str:
    best = None
    best_v = -1.0
    for arm in ARMS:
        v = float(means.get(arm, 0.0))
        if v > best_v:
            best = arm
            best_v = v
    return best or ARMS[0]


def choose_arm_biased(
    arm_means: Dict[str, float],
    guidance_items: List[Dict],
    *,
    eps_bias: float = EPS_BIAS,
) -> Tuple[str, Dict[str, float]]:
    """Deterministic selection using biased means (no exploration in this helper).

    Returns (arm, delta_by_arm).
    """
    biased_means, delta = apply_guidance_bias(
        arm_means, guidance_items, eps_bias=eps_bias
    )
    arm = _best_arm_from_means(biased_means)
    return arm, delta


# Reward computation helpers


def _ias_at_tick(events: List[Dict], tick_no: int) -> float:
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
    events: List[Dict], kind: str, start_tick: int, end_tick: int
) -> int:
    # Determine id ranges
    tick_ids = [
        int(ev.get("id") or 0) for ev in events if ev.get("kind") == "autonomy_tick"
    ]
    if not tick_ids:
        return 0

    def _tick_to_id(t: int) -> Optional[int]:
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
    events: List[Dict], *, horizon: int = 3
) -> Tuple[float, Optional[str], Optional[int]]:
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


def maybe_log_reward(eventlog, *, horizon: int = 3) -> Optional[int]:
    """If sufficient ticks have passed since the last bandit_arm_chosen, append bandit_reward.
    Returns new event id or None if not emitted.
    """
    events = eventlog.read_all()
    # Current tick
    tick_now = _current_tick(events)
    # Build FIFO of chosen arms with ticks and mark rewards to find the oldest unmatched choice
    chosen_queue: List[Tuple[str, int]] = []
    rewarded_counts: List[str] = []
    for ev in events:
        k = ev.get("kind")
        if k == "bandit_arm_chosen":
            m = ev.get("meta") or {}
            arm = str(m.get("arm") or "")
            try:
                t = int(m.get("tick") or 0)
            except Exception:
                t = 0
            chosen_queue.append((arm, t))
        elif k == "bandit_reward":
            m = ev.get("meta") or {}
            arm = str(m.get("arm") or "")
            rewarded_counts.append(arm)
    # Pop off matched choices one-by-one by arm occurrence order
    unmatched: Optional[Tuple[str, int]] = None
    arm_match_progress: Dict[str, int] = {}
    for arm, t in chosen_queue:
        count_used = arm_match_progress.get(arm, 0)
        if rewarded_counts.count(arm) > count_used:
            arm_match_progress[arm] = count_used + 1
            continue  # matched
        unmatched = (arm, t)
        break
    if not unmatched:
        return None
    arm_u, tick_chosen = unmatched
    if tick_chosen <= 0 or (tick_now - tick_chosen) < horizon:
        return None
    reward, arm_calc, _ = compute_reward(events, horizon=horizon)
    arm_final = arm_calc or arm_u
    # Append reward
    return eventlog.append(
        kind="bandit_reward",
        content="",
        meta={"arm": arm_final, "reward": float(reward), "tick": tick_now},
    )
