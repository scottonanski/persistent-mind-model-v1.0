from typing import List, Dict, Any, Optional

TAIL = 400
COMP_PERF = "performance"
LOW_WINRATE = 0.25
HIGH_SAMENESS = 0.80
NOVELTY_STEP = 0.05
NOVELTY_DEC_STEP = 0.05
SKIP_STREAK_THRESHOLD = 3
PLATEAU_TICKS = 4
PLATEAU_EPS = 0.01
THROUGHPUT_WINDOW = 120
MIN_COMMIT_OPEN_FOR_THROUGHPUT = 2


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


def _recent_autonomy_ticks(tail: List[dict], limit: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in reversed(tail):
        if ev.get("kind") != "autonomy_tick":
            continue
        meta = ev.get("meta") or {}
        telem = meta.get("telemetry") or {}
        reflect = meta.get("reflect") or {}
        try:
            ias = float(telem.get("IAS", 0.0))
        except Exception:
            ias = 0.0
        try:
            gas = float(telem.get("GAS", 0.0))
        except Exception:
            gas = 0.0
        out.append(
            {
                "ias": ias,
                "gas": gas,
                "did": bool(reflect.get("did")),
                "reason": str(reflect.get("reason") or ""),
            }
        )
        if len(out) >= limit:
            break
    return out


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

    ticks = _recent_autonomy_ticks(
        tail, limit=max(SKIP_STREAK_THRESHOLD, PLATEAU_TICKS)
    )
    # Reflection skip streaks (due_to_min_turns / due_to_low_novelty)
    if ticks:
        streak_counts = {"due_to_min_turns": 0, "due_to_low_novelty": 0}
        for tinfo in ticks:
            if tinfo["did"]:
                break
            reason = tinfo["reason"]
            if reason in streak_counts:
                streak_counts[reason] += 1
            else:
                break
        if streak_counts["due_to_min_turns"] >= SKIP_STREAK_THRESHOLD:
            current = _last_policy_params(tail, "reflection")
            min_turns = int(current.get("min_turns", 2))
            new_params = {"min_turns": max(1, min_turns - 1)}
            if new_params != {k: current.get(k) for k in new_params.keys()}:
                return _append(
                    eventlog,
                    "curriculum_update",
                    {
                        "proposed": {
                            "component": "reflection",
                            "params": new_params,
                        },
                        "reason": (
                            f"reflect_skip_streak(due_to_min_turns)={streak_counts['due_to_min_turns']}"
                        ),
                        "tick": int(tick),
                    },
                )
        if streak_counts["due_to_low_novelty"] >= SKIP_STREAK_THRESHOLD:
            current = _last_policy_params(tail, "cooldown")
            try:
                thr = float(current.get("novelty_threshold", 0.50))
            except Exception:
                thr = 0.50
            new_thr = max(0.05, thr - NOVELTY_DEC_STEP)
            new_params = {"novelty_threshold": new_thr}
            if new_params != {k: current.get(k) for k in new_params.keys()}:
                return _append(
                    eventlog,
                    "curriculum_update",
                    {
                        "proposed": {
                            "component": "cooldown",
                            "params": new_params,
                        },
                        "reason": (
                            f"reflect_skip_streak(due_to_low_novelty)={streak_counts['due_to_low_novelty']}"
                        ),
                        "tick": int(tick),
                    },
                )

    # Commitment throughput drops: many opens without closes in recent window
    opens = closes = 0
    recent_window = tail[-THROUGHPUT_WINDOW:]
    for ev in recent_window:
        kind = ev.get("kind")
        if kind == "commitment_open":
            opens += 1
        elif kind == "commitment_close":
            closes += 1
    if opens >= MIN_COMMIT_OPEN_FOR_THROUGHPUT and closes == 0:
        current = _last_policy_params(tail, "reflection")
        min_turns = int(current.get("min_turns", 2))
        new_params = {"min_turns": max(1, min_turns - 1)}
        if new_params != {k: current.get(k) for k in new_params.keys()}:
            return _append(
                eventlog,
                kind="curriculum_update",
                meta={
                    "proposed": {
                        "component": "reflection",
                        "params": new_params,
                    },
                    "reason": (
                        f"commitment_throughput(opens={opens}, closes={closes})"
                    ),
                    "tick": int(tick),
                },
            )

    # IAS/GAS plateau detection – little movement across recent ticks
    if ticks and len(ticks) >= PLATEAU_TICKS:
        recent = ticks[:PLATEAU_TICKS]
        ias_vals = [t["ias"] for t in recent]
        gas_vals = [t["gas"] for t in recent]
        if (
            max(ias_vals) - min(ias_vals) <= PLATEAU_EPS
            and max(gas_vals) - min(gas_vals) <= PLATEAU_EPS
        ):
            current = _last_policy_params(tail, "reflection")
            try:
                min_time = int(current.get("min_time_s", 20))
            except Exception:
                min_time = 20
            new_time = max(5, min_time - 10)
            new_params = {"min_time_s": new_time}
            if new_params != {k: current.get(k) for k in new_params.keys()}:
                ias_str = ",".join(f"{v:.2f}" for v in reversed(ias_vals))
                gas_str = ",".join(f"{v:.2f}" for v in reversed(gas_vals))
                return _append(
                    eventlog,
                    kind="curriculum_update",
                    meta={
                        "proposed": {
                            "component": "reflection",
                            "params": new_params,
                        },
                        "reason": (
                            f"ias_gas_plateau(ias=[{ias_str}], gas=[{gas_str}])"
                        ),
                        "tick": int(tick),
                    },
                )

    return None
