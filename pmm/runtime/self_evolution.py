from __future__ import annotations

from typing import Any

from pmm.config import (
    REFLECTION_SKIPPED,
)


class SelfEvolution:
    """Applies intrinsic, append-only self-evolution policies.

    Policies implemented (Stage 1):
    - Adaptive Reflection Cooldown: adjust novelty threshold based on recent skips/success.
    - Personality Drift (Conscientiousness stub): nudge trait based on recent commitment close rate.
    """

    # Defaults (must match runtime when not previously evolved)
    DEFAULT_NOVELTY_THRESHOLD = 0.2
    NOVELTY_MIN = 0.1
    NOVELTY_MAX = 0.9

    DEFAULT_CONSCIENTIOUSNESS = 0.5

    @staticmethod
    def _last_setting_from_evolution(events: list[dict], key: str, default: Any) -> Any:
        """Scan evolution events to retrieve the last known value for `key`.
        key examples: 'cooldown.novelty_threshold', 'traits.Conscientiousness'
        """
        val = default
        for ev in events:
            if ev.get("kind") != "evolution":
                continue
            changes = (ev.get("meta") or {}).get("changes") or {}
            if key in changes:
                val = changes[key]
        return val

    @staticmethod
    def _consecutive_tail(events: list[dict], predicate) -> int:
        cnt = 0
        for ev in reversed(events):
            if predicate(ev):
                cnt += 1
            else:
                break
        return cnt

    @classmethod
    def _adaptive_cooldown(cls, events: list[dict]) -> dict[str, Any]:
        changes: dict[str, Any] = {}

        # Recognize reflection skip events for novelty_low
        def is_skip_novelty_low(ev: dict) -> bool:
            if ev.get("kind") == REFLECTION_SKIPPED:
                meta = ev.get("meta") or {}
                return meta.get("reason") == "due_to_low_novelty"
            return False

        def is_reflection(ev: dict) -> bool:
            return ev.get("kind") == "reflection"

        # Consider only reflection-relevant events when computing consecutive tails,
        # so unrelated trailing events do not break the streak.
        relevant = [
            e for e in events if e.get("kind") in {"reflection", REFLECTION_SKIPPED}
        ]
        skips = cls._consecutive_tail(relevant, is_skip_novelty_low)
        succ = cls._consecutive_tail(relevant, is_reflection)

        current = cls._last_setting_from_evolution(
            events, "cooldown.novelty_threshold", cls.DEFAULT_NOVELTY_THRESHOLD
        )
        new_val = current
        if skips > 3:
            new_val = max(cls.NOVELTY_MIN, float(current) - 0.05)
        elif succ > 3:
            new_val = min(cls.NOVELTY_MAX, float(current) + 0.05)

        if new_val != current:
            changes["cooldown.novelty_threshold"] = new_val
        return changes

    @classmethod
    def _commitment_drift(cls, events: list[dict]) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        # Collect the last 10 commitment_open cids (in order)
        opens: list[str] = []
        for ev in events:
            if ev.get("kind") == "commitment_open":
                cid = (ev.get("meta") or {}).get("cid")
                if cid:
                    opens.append(cid)
        opens = opens[-10:]
        if not opens:
            return changes

        # Count closes for those cids (exclude expirations for completion rate)
        closed = set()
        open_set = set(opens)
        for ev in events:
            if ev.get("kind") == "commitment_close":
                cid = (ev.get("meta") or {}).get("cid")
                if cid in open_set:
                    closed.add(cid)
        rate = len(closed) / float(len(opens))

        current = cls._last_setting_from_evolution(
            events, "traits.Conscientiousness", cls.DEFAULT_CONSCIENTIOUSNESS
        )
        new_val = current
        if rate > 0.8:
            new_val = min(1.0, float(current) + 0.01)
        elif rate < 0.2:
            new_val = max(0.0, float(current) - 0.01)

        if new_val != current:
            changes["traits.Conscientiousness"] = new_val
        return changes

    @classmethod
    def apply_policies(
        cls, events: list[dict], metrics: dict[str, float]
    ) -> tuple[dict[str, Any], str]:
        """Apply self-evolution rules based on recent events and metrics.
        Return (dict of changes applied, details string for telemetry).
        """
        changes: dict[str, Any] = {}
        details = []
        # Adaptive reflection cooldown
        cooldown_changes = cls._adaptive_cooldown(events)
        if cooldown_changes:
            changes.update(cooldown_changes)
            details.append(f"Cooldown: {cooldown_changes}")
        # Personality drift stub
        drift_changes = cls._commitment_drift(events)
        if drift_changes:
            changes.update(drift_changes)
            details.append(f"Drift: {drift_changes}")
        # Commitment completion rate
        recent_commits = [e for e in events[-20:] if e.get("kind") == "commitment_open"]
        recent_closes = [e for e in events[-20:] if e.get("kind") == "commitment_close"]
        if recent_commits and not recent_closes:
            changes["reflection_cadence"] = "increase"
            details.append(
                "No commitments closed in last 20 events, suggest increasing reflection cadence."
            )
        # Reflection novelty
        recent_reflections = [e for e in events[-20:] if e.get("kind") == "reflection"]
        if recent_reflections:
            novel = any(
                "novelty" in (e.get("meta") or {}) and (e["meta"]["novelty"] > 0.5)
                for e in recent_reflections
            )
            if not novel:
                changes["reflection_prompt"] = "make more novel"
                details.append(
                    "Recent reflections lack novelty, suggest more creative prompt."
                )
        # User feedback
        feedback = [e for e in events[-20:] if e.get("kind") == "user_feedback"]
        if feedback:
            changes["user_feedback"] = feedback[-1].get("content")
            details.append(f"User feedback: {feedback[-1].get('content')}")
        return changes, "; ".join(details)


# -------------------- S4(E): Trait Ratchet (deterministic, monotonic) --------------------
# No env flags; all constants here
RATCHET_MIN_REFLECTIONS = 3
RATCHET_MIN_TICK_GAP = 5
RATCHET_STEP = 0.01

RATCHET_BOUNDS = {
    "S0": {
        "openness": (0.40, 0.60),
        "conscientiousness": (0.45, 0.55),
        "extraversion": (0.45, 0.55),
    },
    "S1": {
        "openness": (0.40, 0.65),
        "conscientiousness": (0.45, 0.60),
        "extraversion": (0.45, 0.60),
    },
    "S2": {
        "openness": (0.40, 0.70),
        "conscientiousness": (0.45, 0.65),
        "extraversion": (0.45, 0.65),
    },
    "S3": {
        "openness": (0.40, 0.75),
        "conscientiousness": (0.45, 0.70),
        "extraversion": (0.45, 0.70),
    },
    "S4": {
        "openness": (0.40, 0.80),
        "conscientiousness": (0.45, 0.75),
        "extraversion": (0.45, 0.75),
    },
}


def _read_tail(evlog, n: int = 600) -> list[dict]:
    try:
        return evlog.read_tail(limit=n)
    except TypeError:  # legacy signature fallback
        return evlog.read_tail(n)  # type: ignore[arg-type]


def _latest_perf_report(tail: list[dict]) -> dict | None:
    for e in reversed(tail):
        if e.get("kind") != "evaluation_report":
            continue
        m = e.get("meta") or {}
        if m.get("component") == "performance":
            return e
    return None


def _last_trait_update_tick(tail: list[dict]) -> int:
    for e in reversed(tail):
        if e.get("kind") == "trait_update":
            try:
                return int((e.get("meta") or {}).get("tick") or 0)
            except Exception:
                return 0
    return 0


def _last_autonomy_tick_id(tail: list[dict]) -> int:
    for e in reversed(tail):
        if e.get("kind") == "autonomy_tick":
            try:
                return int(e.get("id") or 0)
            except Exception:
                return 0
    return 0


def _ratchet_emitted_this_tick(tail: list[dict]) -> bool:
    last_auto_id = _last_autonomy_tick_id(tail)
    for e in reversed(tail):
        try:
            eid = int(e.get("id") or 0)
        except Exception:
            continue
        if last_auto_id and eid <= last_auto_id:
            break
        if (
            e.get("kind") == "trait_update"
            and (e.get("meta") or {}).get("reason") == "ratchet"
        ):
            return True
    return False


def propose_trait_ratchet(eventlog, *, tick: int, stage: str) -> int | None:
    """Propose a monotonic trait ratchet as a single combined trait_update.

    Gates:
    - At least RATCHET_MIN_REFLECTIONS since last ratchet
    - Last trait_update at least RATCHET_MIN_TICK_GAP ticks ago
    - At most once per tick (skip if a ratchet already emitted since last autonomy_tick)
    """
    tail = _read_tail(eventlog, n=1000)
    # Single-emission per tick
    if _ratchet_emitted_this_tick(tail):
        return None

    # Reflections since last ratchet
    last_ratchet_id = 0
    for e in reversed(tail):
        if (
            e.get("kind") == "trait_update"
            and (e.get("meta") or {}).get("reason") == "ratchet"
        ):
            try:
                last_ratchet_id = int(e.get("id") or 0)
            except Exception:
                last_ratchet_id = 0
            break
    refl_cnt = 0
    for e in tail:
        try:
            eid = int(e.get("id") or 0)
        except Exception:
            continue
        if eid > last_ratchet_id and e.get("kind") == "reflection":
            refl_cnt += 1
    if refl_cnt < RATCHET_MIN_REFLECTIONS:
        return None

    # Tick-gap gate for any trait_update
    last_trait_tick = _last_trait_update_tick(tail)
    try:
        curr_tick = int(tick)
    except Exception:
        curr_tick = 0
    if last_trait_tick and (curr_tick - last_trait_tick) < int(RATCHET_MIN_TICK_GAP):
        return None

    # Current identity traits (bounded tail projection is acceptable)
    try:
        from pmm.storage.projection import build_identity as _build_identity

        ident = _build_identity(tail)
    except Exception:
        ident = {
            "traits": {"openness": 0.5, "conscientiousness": 0.5, "extraversion": 0.5}
        }
    traits = (ident.get("traits") or {}).copy()
    opn = float(traits.get("openness", 0.5))
    con = float(traits.get("conscientiousness", 0.5))
    ext = float(traits.get("extraversion", 0.5))

    # Metrics hints from latest performance report
    rpt = _latest_perf_report(tail)
    metrics = (rpt.get("meta") or {}).get("metrics") if rpt else {}
    try:
        same = float((metrics or {}).get("novelty_same_ratio", 0.0) or 0.0)
    except Exception:
        same = 0.0
    try:
        win = float((metrics or {}).get("bandit_accept_winrate", 0.0) or 0.0)
    except Exception:
        win = 0.0

    # Proposed deltas
    d_opn = 0.0
    d_con = 0.0
    d_ext = 0.0
    if same > 0.80:
        d_opn += RATCHET_STEP
    if win < 0.25:
        d_con += RATCHET_STEP
        # If heavy reflection volume but flat acceptance, reduce verbosity proxy
        if refl_cnt >= RATCHET_MIN_REFLECTIONS:
            d_ext -= RATCHET_STEP

    # Clamp to stage bounds
    bounds = RATCHET_BOUNDS.get(str(stage), RATCHET_BOUNDS.get("S0"))

    def _clamp(val: float, mn: float, mx: float) -> float:
        return max(mn, min(mx, val))

    new_opn = _clamp(opn + d_opn, *bounds["openness"]) if bounds else (opn + d_opn)
    new_con = (
        _clamp(con + d_con, *bounds["conscientiousness"]) if bounds else (con + d_con)
    )
    new_ext = _clamp(ext + d_ext, *bounds["extraversion"]) if bounds else (ext + d_ext)

    # Final deltas after clamp
    f_opn = round(new_opn - opn, 3)
    f_con = round(new_con - con, 3)
    f_ext = round(new_ext - ext, 3)

    if f_opn == 0.0 and f_con == 0.0 and f_ext == 0.0:
        return None

    meta = {
        "delta": {
            "openness": f_opn,
            "conscientiousness": f_con,
            "extraversion": f_ext,
        },
        "tick": int(curr_tick),
        "reason": "ratchet",
        "stage": str(stage),
    }
    return eventlog.append(kind="trait_update", content="", meta=meta)
