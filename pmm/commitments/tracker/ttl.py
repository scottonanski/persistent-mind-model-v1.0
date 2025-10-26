"""TTL logic scaffolding (Stage 2).

Provides signatures for tick-driven TTL evaluation without wiring into the
legacy tracker yet. This allows tests and future modules to import stable
entrypoints when we migrate.

Semantics:
- Hours-based TTL uses event timestamps (ISO 8601) for age calculations.
- Tick-based helpers are pure and rely on counting `autonomy_tick` events; do not mix with hours TTL in the same call.
- Functions are deterministic and have no side effects.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable


def compute_current_tick(events: Iterable[dict]) -> int:
    """Compute a simple tick counter from events (autonomy_tick based).

    Pure helper for TTL reasoning; not wired yet. Counts autonomy_tick events
    and returns the next tick index.
    """
    count = 0
    for e in events:
        if (e.get("kind") or "") == "autonomy_tick":
            count += 1
    return count + 1


def ttl_expire_at(open_tick: int, ttl_ticks: int) -> int:
    """Return the tick index at which this item should expire.

    Pure boundary function: open_tick + ttl_ticks (clamped to >= open_tick).
    """
    ttl_ticks = max(0, int(ttl_ticks))
    open_tick = max(0, int(open_tick))
    return open_tick + ttl_ticks


def last_activity_tick(events: Iterable[dict], *, cid: str) -> int | None:
    """Return the last activity tick for a given commitment (open/update/close).

    Pure helper; uses autonomy_tick counting to outline boundary behavior.
    Returns None if commitment was never seen in the stream.
    """
    current_tick = 0
    last_tick: int | None = None
    for e in events:
        if (e.get("kind") or "") == "autonomy_tick":
            current_tick += 1
        kind = e.get("kind") or ""
        m = e.get("meta") or {}
        if kind in {
            "commitment_open",
            "commitment_update",
            "commitment_close",
            "commitment_expire",
        }:
            if str(m.get("cid") or "") == str(cid):
                last_tick = current_tick
    return last_tick


def compute_expired(
    events: Iterable[dict], *, ttl_hours: int, now_iso: str | None = None
) -> list[tuple[str, int]]:
    """Return list of (cid, expire_at_tick_placeholder) for commitments expired by hours.

    Pure, hours-based evaluation to match legacy semantics used by
    `expire_old_commitments()`. The second tuple element is a placeholder (-1)
    for compatibility; callers should not rely on it for hours-based TTL.
    """
    ttl_hours = max(0, int(ttl_hours))
    if ttl_hours == 0:
        return []

    # Build open-set and map first open timestamp per cid
    open_map: dict[str, dict] = {}
    opened_ts: dict[str, str] = {}
    closed: set[str] = set()
    for ev in events:
        kind = ev.get("kind") or ""
        meta = ev.get("meta") or {}
        if kind == "commitment_open":
            cid = str(meta.get("cid") or "")
            if cid and cid not in opened_ts and cid not in closed:
                open_map[cid] = meta
                ts = ev.get("ts")
                if ts:
                    opened_ts[cid] = str(ts)
        elif kind in {"commitment_close", "commitment_expire"}:
            cid = str(meta.get("cid") or "")
            if cid:
                closed.add(cid)
                open_map.pop(cid, None)
                opened_ts.pop(cid, None)

    # Determine current time ISO
    if now_iso is None:
        now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    now_dt = _dt.datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))

    expired: list[tuple[str, int]] = []
    for cid, ts in opened_ts.items():
        try:
            open_dt = _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            continue
        age_hours = (now_dt - open_dt).total_seconds() / 3600.0
        if age_hours >= ttl_hours:
            expired.append((cid, -1))
    return expired


__all__ = [
    "compute_current_tick",
    "ttl_expire_at",
    "last_activity_tick",
    "compute_expired",
]
