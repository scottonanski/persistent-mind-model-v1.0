from __future__ import annotations
from typing import Dict, List, Optional

# Stable analysis windows (no env flags)
EVAL_TAIL_EVENTS: int = 400
METRICS_WINDOW: int = 200  # last-N events considered for metrics
COMPONENT_PERFORMANCE: str = "performance"


def _last_n(events: List[dict], n: int) -> List[dict]:
    if n <= 0:
        return []
    return events[-n:] if len(events) > n else list(events)


def _safe_div(num: float, den: float) -> float:
    return 0.0 if den <= 0 else (num / den)


def _get_meta(e: dict) -> dict:
    m = e.get("meta")
    return m if isinstance(m, dict) else {}


def compute_performance_metrics(
    events: List[dict], window: int = METRICS_WINDOW
) -> Dict[str, float]:
    """
    Deterministic, order-insensitive metrics computed over the last `window` events.
    Inputs are raw event dicts already from a tail read. No wall-clock used.
    """
    slice_ = _last_n(events, window)

    # Commitment completion rate (exclude expirations)
    opens = closes = expires = 0
    for e in slice_:
        k = e.get("kind")
        if k == "commitment_open":
            opens += 1
        elif k == "commitment_close":
            closes += 1
        elif k == "commitment_expire":
            expires += 1
    eligible = max(0, opens - expires)  # “exclude expirations” from denominator
    completion_rate = _safe_div(closes, eligible if eligible > 0 else max(1, opens))

    # Bandit reflect acceptance winrate (from bandit_reward events)
    # Convention: reward > 0.0 => accepted/good; else 0.0
    br_total = br_pos = 0
    for e in slice_:
        if e.get("kind") == "bandit_reward":
            br_total += 1
            reward = float(_get_meta(e).get("reward", 0.0) or 0.0)
            if reward > 0.0:
                br_pos += 1
    bandit_accept_winrate = _safe_div(br_pos, br_total)

    # LLM latency (chat) mean in ms
    lat_sum = lat_count = 0
    for e in slice_:
        if e.get("kind") == "llm_latency":
            meta = _get_meta(e)
            if str(meta.get("op")) == "chat":
                try:
                    ms = float(meta.get("ms", 0.0) or 0.0)
                except Exception:
                    ms = 0.0
                lat_sum += ms
                lat_count += 1
    llm_chat_latency_mean_ms = _safe_div(lat_sum, lat_count)

    # Novelty trend “same” ratio from audit_report(category='novelty_trend')
    nov_total = nov_same = 0
    for e in slice_:
        if e.get("kind") == "audit_report":
            meta = _get_meta(e)
            if meta.get("category") == "novelty_trend":
                nov_total += 1
                if meta.get("value") == "same":
                    nov_same += 1
    novelty_same_ratio = _safe_div(nov_same, nov_total)

    return {
        "completion_rate": float(completion_rate),
        "bandit_accept_winrate": float(bandit_accept_winrate),
        "llm_chat_latency_mean_ms": float(llm_chat_latency_mean_ms),
        "novelty_same_ratio": float(novelty_same_ratio),
        "window": float(window),
    }


def _find_existing_report_for_tick(events_tail: List[dict], tick: int) -> Optional[int]:
    # Scan a bounded tail for an existing evaluation_report for this tick.
    for e in reversed(_last_n(events_tail, EVAL_TAIL_EVENTS)):
        if e.get("kind") != "evaluation_report":
            continue
        meta = _get_meta(e)
        if (
            int(meta.get("tick", -1)) == int(tick)
            and meta.get("component") == COMPONENT_PERFORMANCE
        ):
            try:
                return int(e.get("id") or 0)
            except Exception:
                return 0
    return None


def emit_evaluation_report(
    eventlog,
    *,
    metrics: Dict[str, float],
    tick: int,
    component: str = COMPONENT_PERFORMANCE,
) -> Optional[int]:
    """
    Append evaluation_report once per tick (idempotent per (component, tick)).
    Returns the new event id or the existing one if already emitted; None on no-op.
    """
    # Read a small tail to check for duplicates deterministically
    try:
        tail = eventlog.read_tail(limit=EVAL_TAIL_EVENTS)
    except TypeError:
        # Older adapter signature
        tail = eventlog.read_tail(EVAL_TAIL_EVENTS)  # type: ignore[arg-type]

    existing = _find_existing_report_for_tick(tail, tick)
    if existing:
        return existing

    try:
        ev_id = eventlog.append(
            kind="evaluation_report",
            content="",
            meta={
                "component": component,
                "metrics": dict(metrics),
                "window": int(metrics.get("window", METRICS_WINDOW)),
                "tick": int(tick),
            },
        )
    except TypeError:
        # Fallback for dict-style append (not expected in this codebase)
        ev_id = eventlog.append(
            {
                "kind": "evaluation_report",
                "content": "",
                "meta": {
                    "component": component,
                    "metrics": dict(metrics),
                    "window": int(metrics.get("window", METRICS_WINDOW)),
                    "tick": int(tick),
                },
            }
        )  # type: ignore[misc]
    return ev_id
