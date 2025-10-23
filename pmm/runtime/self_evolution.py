from __future__ import annotations

from typing import Any

from pmm.config import (
    REFLECTION_SKIPPED,
)
from pmm.runtime.traits import normalize_key
from pmm.storage.projection import build_identity


def _read_trait_val(traits: dict, name: str, default: float = 0.0) -> float:
    """Read a trait value tolerating legacy capitalization."""
    name_l = normalize_key(name)
    candidates = (
        name_l,
        name_l.capitalize(),
        f"traits.{name_l}",
        f"traits.{name_l.capitalize()}",
    )
    for cand in candidates:
        if cand in traits:
            try:
                return float(traits[cand])
            except Exception:
                return default
    return default


class SelfEvolution:
    """Applies intrinsic, append-only self-evolution policies."""

    DEFAULT_NOVELTY_THRESHOLD = 0.2
    NOVELTY_MIN = 0.1
    NOVELTY_MAX = 0.9

    @staticmethod
    def _last_setting_from_evolution(events: list[dict], key: str, default: Any) -> Any:
        """Scan evolution events to retrieve the last known value for `key`."""
        val = default
        key_candidates = {key}
        if key.startswith("traits."):
            suffix = key.split(".", 1)[1]
            norm = normalize_key(suffix)
            key_candidates.update(
                {
                    f"traits.{norm}",
                    f"traits.{suffix}",
                    f"traits.{suffix.capitalize()}",
                    f"traits.{norm.capitalize()}",
                }
            )
        else:
            norm = normalize_key(key)
            key_candidates.update({norm, norm.capitalize()})
        for ev in events:
            if ev.get("kind") != "evolution":
                continue
            changes = (ev.get("meta") or {}).get("changes") or {}
            for cand in key_candidates:
                if cand in changes:
                    val = changes[cand]
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

        def is_skip_novelty_low(ev: dict) -> bool:
            if ev.get("kind") == REFLECTION_SKIPPED:
                meta = ev.get("meta") or {}
                return meta.get("reason") == "due_to_low_novelty"
            return False

        def is_reflection(ev: dict) -> bool:
            return ev.get("kind") == "reflection"

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
    def _semantic_trait_drift(
        cls, events: list[dict], trait_drift_manager
    ) -> dict[str, Any]:
        if not trait_drift_manager:
            return {}

        all_deltas = []
        for event in events[-20:]:
            if event.get("kind") in ["user", "response"] and event.get("content"):
                try:
                    deltas = trait_drift_manager.apply_event_effects(event, {})
                    all_deltas.extend(deltas)
                except Exception:
                    continue

        if not all_deltas:
            return {}

        aggregated_deltas = {}
        for delta_item in all_deltas:
            trait = delta_item["trait"]
            delta = delta_item["delta"]
            if trait not in aggregated_deltas:
                aggregated_deltas[trait] = 0.0
            aggregated_deltas[trait] += delta

        try:
            identity = build_identity(events)
            current_traits = identity.get("traits", {})
        except Exception:
            current_traits = {}

        changes = {}
        for trait_code, total_delta in aggregated_deltas.items():
            trait_name = {
                "O": "openness",
                "C": "conscientiousness",
                "E": "extraversion",
                "A": "agreeableness",
                "N": "neuroticism",
            }.get(trait_code.upper())
            if not trait_name:
                continue

            trait_key = f"traits.{trait_name}"
            current_value = _read_trait_val(current_traits, trait_name, 0.5)

            capped_delta = max(-0.1, min(0.1, total_delta))

            new_value = current_value + capped_delta
            new_value = max(0.0, min(1.0, new_value))

            if abs(new_value - current_value) > 1e-4:
                changes[trait_key] = round(new_value, 4)

        return changes

    @classmethod
    def apply_policies(
        cls, events: list[dict], metrics: dict[str, float], trait_drift_manager=None
    ) -> tuple[dict[str, Any], str]:
        """Apply self-evolution rules based on recent events and metrics."""
        changes: dict[str, Any] = {}
        details = []

        cooldown_changes = cls._adaptive_cooldown(events)
        if cooldown_changes:
            changes.update(cooldown_changes)
            details.append(f"Cooldown: {cooldown_changes}")

        semantic_drift_changes = cls._semantic_trait_drift(events, trait_drift_manager)
        if semantic_drift_changes:
            changes.update(semantic_drift_changes)
            details.append(f"SemanticDrift: {semantic_drift_changes}")

        recent_commits = [e for e in events[-20:] if e.get("kind") == "commitment_open"]
        recent_closes = [e for e in events[-20:] if e.get("kind") == "commitment_close"]
        if recent_commits and not recent_closes:
            changes["reflection_cadence"] = "increase"
            details.append(
                "No commitments closed in last 20 events, suggest increasing reflection cadence."
            )

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

        feedback = [e for e in events[-20:] if e.get("kind") == "user_feedback"]
        if feedback:
            changes["user_feedback"] = feedback[-1].get("content")
            details.append(f"User feedback: {feedback[-1].get('content')}")

        return changes, "; ".join(details)


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
    except TypeError:
        return evlog.read_tail(n)


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
    """Propose a monotonic trait ratchet as a single combined trait_update."""
    tail = _read_tail(eventlog, n=1000)
    if _ratchet_emitted_this_tick(tail):
        return None

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

    last_trait_tick = _last_trait_update_tick(tail)
    try:
        curr_tick = int(tick)
    except Exception:
        curr_tick = 0
    if last_trait_tick and (curr_tick - last_trait_tick) < int(RATCHET_MIN_TICK_GAP):
        return None

    try:
        ident = build_identity(tail)
    except Exception:
        ident = {
            "traits": {"openness": 0.5, "conscientiousness": 0.5, "extraversion": 0.5}
        }
    traits = (ident.get("traits") or {}).copy()
    opn = _read_trait_val(traits, "openness", 0.5)
    con = _read_trait_val(traits, "conscientiousness", 0.5)
    ext = _read_trait_val(traits, "extraversion", 0.5)

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

    d_opn = 0.0
    d_con = 0.0
    d_ext = 0.0
    if same > 0.80:
        d_opn += RATCHET_STEP
    if win < 0.25:
        d_con += RATCHET_STEP
        if refl_cnt >= RATCHET_MIN_REFLECTIONS:
            d_ext -= RATCHET_STEP

    bounds = RATCHET_BOUNDS.get(str(stage), RATCHET_BOUNDS.get("S0"))

    def _clamp(val: float, mn: float, mx: float) -> float:
        return max(mn, min(mx, val))

    new_opn = _clamp(opn + d_opn, *bounds["openness"]) if bounds else (opn + d_opn)
    new_con = (
        _clamp(con + d_con, *bounds["conscientiousness"]) if bounds else (con + d_con)
    )
    new_ext = _clamp(ext + d_ext, *bounds["extraversion"]) if bounds else (ext + d_ext)

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
