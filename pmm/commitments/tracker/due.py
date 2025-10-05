"""Due-date logic scaffolding (Stage 2).

Placeholder for due-date calculations and scheduling hooks. Not wired yet to
the legacy tracker; exists to enable incremental migration without behavior
changes.

Semantics:
- Selects reflection-driven opens still in the open set at evaluation time.
- Computes `due_epoch = open_ts + horizon_hours * 3600` using ISO timestamps.
- Skips cids with future snooze (`until_tick > current_tick`) or already due.
- Deterministic and side-effect free.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable


def compute_due(
    events: Iterable[dict], *, horizon_hours: int, now_epoch: int
) -> list[tuple[str, int]]:
    """Return (cid, due_epoch) that are due now for reflection-driven opens.

    Rules (pure, deterministic):
    - Select commitments opened with meta.reason == "reflection" that are still open (no close/expire).
    - Compute due_epoch = open_ts + horizon_hours*3600.
    - Skip if a commitment_snooze exists with until_tick > current_tick.
    - Skip if a commitment_due already exists for that cid.
    - Return only those whose due_epoch <= now_epoch.
    """
    horizon_s = max(0, int(horizon_hours)) * 3600
    now_epoch = int(now_epoch)

    # Current tick count
    current_tick = sum(1 for e in events if (e.get("kind") or "") == "autonomy_tick")

    # Build open-set and ts for reflection-driven opens; track closes/expires
    opened_ts: dict[str, str] = {}
    closed_or_expired: set[str] = set()
    for e in events:
        k = e.get("kind") or ""
        m = e.get("meta") or {}
        if k == "commitment_open":
            cid = str(m.get("cid") or "")
            if cid and cid not in closed_or_expired and cid not in opened_ts:
                if (m.get("reason") or "").strip() == "reflection":
                    ts = e.get("ts")
                    if ts:
                        opened_ts[cid] = str(ts)
        elif k in {"commitment_close", "commitment_expire"}:
            cid = str(m.get("cid") or "")
            if cid:
                closed_or_expired.add(cid)
                opened_ts.pop(cid, None)

    # Snooze map (latest wins)
    snooze_until: dict[str, int] = {}
    for e in events:
        if (e.get("kind") or "") == "commitment_snooze":
            m = e.get("meta") or {}
            cid = str(m.get("cid") or "")
            try:
                until_t = int(m.get("until_tick") or 0)
            except Exception:
                until_t = 0
            if cid:
                snooze_until[cid] = max(snooze_until.get(cid, 0), until_t)

    # Already due set
    already_due: set[str] = set(
        str((e.get("meta") or {}).get("cid") or "")
        for e in events
        if (e.get("kind") or "") == "commitment_due"
    )

    out: list[tuple[str, int]] = []
    for cid, ts in opened_ts.items():
        # Skip snoozed
        if cid in snooze_until and current_tick <= snooze_until[cid]:
            continue
        try:
            open_dt = _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            continue
        due_epoch = int(open_dt.timestamp()) + horizon_s
        if due_epoch <= now_epoch and cid not in already_due:
            out.append((cid, due_epoch))
    return out


__all__ = ["compute_due"]
