"""Tick helper functions extracted from the autonomy loop.

These helpers are pure and bounded; they operate on provided inputs only.
"""

from __future__ import annotations

import hashlib as _hashlib

from pmm.storage.eventlog import EventLog


def _has_reflection_since_last_tick(
    eventlog: EventLog, events: list[dict] | None = None
) -> bool:
    if events is None:
        try:
            evs = eventlog.read_tail(limit=1000)
        except Exception:
            try:
                evs = eventlog.read_all()
            except Exception:
                return False
    else:
        evs = events
    last_tick_id = None
    for ev in reversed(evs):
        if ev.get("kind") == "autonomy_tick":
            try:
                last_tick_id = int(ev.get("id") or 0)
            except Exception:
                pass
            break
    if last_tick_id is None:
        return False
    for ev in reversed(evs):
        try:
            eid = int(ev.get("id") or 0)
        except Exception:
            continue
        if eid <= last_tick_id:
            break
        if ev.get("kind") == "reflection":
            return True
    return False


def generate_system_status_reflection(
    ias: float, gas: float, stage_str: str, eventlog: EventLog, tick_id: int = None
) -> str:
    import hashlib

    if tick_id is None:
        try:
            tick_id = int(eventlog.get_max_id())
        except Exception:
            try:
                tick_id = len(eventlog.read_tail(limit=1000))
            except Exception:
                tick_id = 0
    hash_suffix = hashlib.sha256(str(tick_id).encode()).hexdigest()[:8]
    try:
        from pmm.commitments.tracker import CommitmentTracker

        tracker = CommitmentTracker(eventlog)
        commitments = tracker.list_open_commitments()
        if commitments:
            commit_summary = "; ".join(
                [f"{c.get('text', '')[:40]}" for c in commitments[:3]]
            )
        else:
            commit_summary = "no commitments"
    except Exception:
        commit_summary = "commitment tracking unavailable"

    return (
        f"System status: IAS={ias:.3f}, GAS={gas:.3f}, Stage={stage_str}.\n"
        f"Reflecting on {commit_summary} (tick {hash_suffix}) at tick {tick_id}.\n"
        f"Current metrics indicate {'active' if ias > 0.5 else 'low'} interaction and "
        f"{'strong' if gas > 0.5 else 'developing'} goal alignment."
    )


def _append_reflection_check(eventlog: EventLog, ref_id: int, text: str) -> None:
    t = str(text or "")
    ok = False
    reason = "empty_reflection"
    if t.strip():
        lines_raw = t.splitlines()
        last_raw = lines_raw[-1] if lines_raw else ""
        if last_raw.strip():
            ok = True
            reason = "last_line_nonempty"
        else:
            ok = False
            reason = "no_final_line"
    from pmm.runtime.loop import io as _io

    _io.append_reflection_check(eventlog, ref=ref_id, ok=ok, reason=reason)


def _resolve_reflection_policy_overrides(
    events: list[dict],
) -> tuple[int | None, int | None]:
    try:
        for ev in reversed(events):
            if ev.get("kind") != "policy_update":
                continue
            m = ev.get("meta") or {}
            if str(m.get("component")) != "reflection":
                continue
            p = m.get("params") or {}
            mt = p.get("min_turns")
            ms = p.get("min_time_s")
            if mt is None or ms is None:
                continue

            # CLAMP POLICY VALUES - Hard-coded sane defaults per CONTRIBUTING.md
            try:
                mt_int = int(mt)
                ms_int = int(ms)
                ms_clamped = max(30, min(120, ms_int))
                mt_clamped = max(1, min(10, mt_int))

                if ms_clamped != ms_int or mt_clamped != mt_int:
                    # Not logging here to keep helpers pure; caller may log
                    pass

                return (mt_clamped, ms_clamped)
            except Exception:
                return (None, None)
    except Exception:
        return (None, None)
    return (None, None)


def _sha256_json(obj) -> str:
    try:
        import json as _json

        return _hashlib.sha256(
            _json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    except Exception:
        return ""


__all__ = [
    "_has_reflection_since_last_tick",
    "generate_system_status_reflection",
    "_append_reflection_check",
    "_resolve_reflection_policy_overrides",
    "_sha256_json",
]
