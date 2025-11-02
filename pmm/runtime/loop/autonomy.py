"""Autonomy helpers extracted from loop.tick.

Pure helpers to keep `loop.py` smaller and easier to reason about.
Functions here must be deterministic and side-effect free.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pmm.runtime.snapshot import LedgerSnapshot
from pmm.storage.projection import build_identity, build_self_model


def _get_current_stage_from_events(events: list[dict]) -> str:
    """Get the current stage from the most recent stage_update event.

    Args:
        events: List of events to search through

    Returns:
        Current stage as string, or 'S0' if no stage_update events found
    """
    # Look for the most recent stage_update event
    for event in reversed(events):
        if event.get("kind") == "stage_update":
            meta = event.get("meta") or {}
            stage = meta.get("to")
            if stage:
                return str(stage)

    # Fallback to inference if no explicit stage updates
    from pmm.runtime.stage_tracker import StageTracker

    stage, _ = StageTracker.infer_stage(events)
    return stage


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


def build_snapshot_fallback(eventlog: Any) -> LedgerSnapshot:
    """Build a bounded snapshot when runtime._get_snapshot() is unavailable."""
    try:
        events = eventlog.read_tail(limit=2000)
    except Exception:
        events = eventlog.read_all()
    identity = build_identity(events)
    self_model = build_self_model(events, eventlog=eventlog)
    from pmm.runtime.metrics import get_or_compute_ias_gas

    ias, gas = get_or_compute_ias_gas(eventlog)
    from pmm.runtime.stage_tracker import StageTracker

    # Get current stage from explicit stage_update events, not inference
    current_stage = _get_current_stage_from_events(events)
    stage, stage_snapshot = StageTracker.infer_stage(events)
    last_id = int(events[-1]["id"]) if events else 0
    return LedgerSnapshot(
        events=list(events),
        identity=identity,
        self_model=self_model,
        ias=ias,
        gas=gas,
        stage=current_stage,
        stage_snapshot=stage_snapshot,
        last_event_id=last_id,
    )


def should_introspect(tick_no: int, introspection_cadence: int) -> bool:
    """Determine if introspection should run on this tick.

    Uses deterministic cadence based on tick number to ensure
    replay consistency and predictable introspection timing.
    """
    return tick_no > 0 and (tick_no % introspection_cadence) == 0


def extract_reflection_claim_ids(reply: str) -> list[int]:
    """Extract reflection event IDs claimed in a reply text.

    Looks for sentences containing 'reflect' and extracts event IDs
    using both extract_event_ids and #123 patterns.
    """
    if not reply:
        return []

    sentences: list[str] = []
    current: list[str] = []
    for char in reply:
        if char in ".!?\n":
            if current:
                sentences.append("".join(current).strip())
                current = []
        else:
            current.append(char)
    if current:
        sentences.append("".join(current).strip())

    seen: set[int] = set()
    results: list[int] = []

    from pmm.utils.parsers import extract_event_ids

    for sentence in sentences:
        lowered = sentence.lower()
        if "reflect" not in lowered:
            continue

        for eid in extract_event_ids(sentence):
            if eid > 0 and eid not in seen:
                seen.add(eid)
                results.append(eid)

        for token in sentence.split():
            if token.startswith("#") and token[1:].isdigit():
                value = int(token[1:])
                if value > 0 and value not in seen:
                    seen.add(value)
                    results.append(value)

    return results


def latest_reflection_ids_from_tail(events_tail: list[dict]) -> list[int]:
    """Return the most recent reflection ID as a singleton list."""
    for ev in reversed(events_tail):
        if ev.get("kind") != "reflection":
            continue
        try:
            rid = int(ev.get("id") or 0)
        except Exception:
            continue
        if rid > 0:
            return [rid]
    return []


def turns_since_last_identity_adopt(events: list[dict]) -> int:
    """Calculate the number of turns since the last identity adoption.

    Returns the number of turns, or -1 if no previous identity adoption is found.
    """
    # Find the last identity_adopt event
    last_adopt_event = None
    for event in reversed(events):
        if event.get("kind") == "identity_adopt":
            last_adopt_event = event
            break

    # If no previous adoption, return -1
    if last_adopt_event is None:
        return -1

    # Find all autonomy_tick events with their IDs
    autonomy_ticks = [
        (int(event.get("id", 0)), event)
        for event in events
        if event.get("kind") == "autonomy_tick"
    ]

    # Find the ID of the last identity adoption
    last_adopt_id = int(last_adopt_event.get("id", 0))

    # Count how many autonomy ticks have happened since the last identity adoption
    ticks_since_last_adopt = 0
    for tick_id, tick_event in reversed(autonomy_ticks):
        if tick_id > last_adopt_id:
            ticks_since_last_adopt += 1
        else:
            break

    return ticks_since_last_adopt


def last_policy_params(
    events: list[dict], component: str
) -> tuple[str | None, dict | None]:
    """Find last policy_update params for a component.
    Returns (stage, params) or (None, None).
    """
    for ev in reversed(events):
        if ev.get("kind") != "policy_update":
            continue
        m = ev.get("meta") or {}
        if str(m.get("component")) != component:
            continue
        stage = m.get("stage")
        params = m.get("params")
        if isinstance(params, dict):
            return (str(stage) if stage is not None else None, params)
    return (None, None)


def append_policy_update(
    eventlog: Any,
    *,
    component: str,
    params: dict | None,
    stage: str | None = None,
    tick: int | None = None,
    extra_meta: dict | None = None,
    dedupe_with_last: bool = True,
) -> int | None:
    """Append a policy_update event with optional dedupe safeguards."""

    try:
        events = eventlog.read_all()
    except Exception:
        events = []

    params_dict = dict(params or {})

    if dedupe_with_last and events:
        _last_stage, last_params = last_policy_params(events, component=component)
        if dict(last_params or {}) == params_dict:
            return None

    meta: dict[str, object] = {
        "component": component,
        "params": params_dict,
    }

    if stage is not None:
        meta["stage"] = stage
    if tick is not None:
        meta["tick"] = tick
    if extra_meta:
        for key, value in extra_meta.items():
            meta[key] = value

    return eventlog.append(kind="policy_update", content="", meta=meta)


def consecutive_reflect_skips(eventlog: Any, reason: str, lookback: int = 8) -> int:
    """Count consecutive reflection skip events for the same reason."""
    try:
        evs = eventlog.read_tail(limit=max(lookback * 4, 64))
    except Exception:
        try:
            evs = eventlog.read_all()
        except Exception:
            return 0
    count = 0
    for ev in reversed(evs):
        if ev.get("kind") != "reflection_skipped":
            break
        m = ev.get("meta") or {}
        if str(m.get("reason")) == str(reason):
            count += 1
        if count >= lookback:
            break
    return count
