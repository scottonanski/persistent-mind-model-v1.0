from __future__ import annotations
from typing import Optional, Dict, Any, List

TAIL = 400
COMP_PERF = "performance"
LOW_WINRATE = 0.25
HIGH_SAMENESS = 0.80
NOVELTY_STEP = 0.05


def _tail(evlog, n: int = TAIL) -> List[dict]:
    try:
        return evlog.read_tail(limit=n)
    except TypeError:  # legacy signature fallback
        return evlog.read_tail(n)  # type: ignore[arg-type]


def _last_policy_params(tail: List[dict], component: str) -> Dict[str, Any]:
    for e in reversed(tail):
        if e.get("kind") != "policy_update":
            continue
        meta = e.get("meta") or {}
        if str(meta.get("component")) == component:
            return dict(meta.get("params") or {})
    return {}


def _latest_perf_report(tail: List[dict]) -> Optional[dict]:
    for e in reversed(tail):
        if e.get("kind") != "evaluation_report":
            continue
        m = e.get("meta") or {}
        if m.get("component") == COMP_PERF:
            return e
    return None


def _append(evlog, kind: str, meta: Dict[str, Any]) -> int:
    return int(evlog.append(kind=kind, content="", meta=meta))


def maybe_propose_curriculum(eventlog, *, tick: int) -> Optional[int]:
    tail = _tail(eventlog)
    rpt = _latest_perf_report(tail)
    if not rpt:
        return None
    metrics = (rpt.get("meta") or {}).get("metrics") or {}
    try:
        win = float(metrics.get("bandit_accept_winrate", 0.0) or 0.0)
    except Exception:
        win = 0.0
    try:
        same = float(metrics.get("novelty_same_ratio", 0.0) or 0.0)
    except Exception:
        same = 0.0

    # Rule 1: low acceptance → reflect more (lower min_turns)
    if win < LOW_WINRATE:
        current = _last_policy_params(tail, "reflection")
        min_turns = int(current.get("min_turns", 2))
        new_params = {"min_turns": max(1, min_turns - 1)}
        # If the proposal equals current, do not emit a new curriculum_update
        if new_params == {k: current.get(k) for k in new_params.keys()}:
            return None
        return _append(
            eventlog,
            kind="curriculum_update",
            meta={
                "proposed": {"component": "reflection", "params": new_params},
                "reason": f"bandit_accept_winrate={win:.2f} < {LOW_WINRATE}",
                "tick": int(tick),
            },
        )

    # Rule 2: high sameness → raise novelty threshold a bit
    if same > HIGH_SAMENESS:
        current = _last_policy_params(tail, "cooldown")
        try:
            thr = float(current.get("novelty_threshold", 0.50))
        except Exception:
            thr = 0.50
        new_params = {"novelty_threshold": min(1.0, thr + NOVELTY_STEP)}
        if new_params == {k: current.get(k) for k in new_params.keys()}:
            return None
        return _append(
            eventlog,
            kind="curriculum_update",
            meta={
                "proposed": {"component": "cooldown", "params": new_params},
                "reason": f"novelty_same_ratio={same:.2f} > {HIGH_SAMENESS}",
                "tick": int(tick),
            },
        )

    return None
