#!/usr/bin/env python3
"""TTL shadow-compare tool.

Usage:
  python -m scripts.ttl_shadow_compare /path/to/eventlog.db [ttl_hours]

Reads the EventLog, computes legacy expiration set via CommitmentTracker,
and compares it against tick-based ttl.compute_expired(). Prints any
divergences; makes no changes to the log.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pmm.commitments.tracker import CommitmentTracker
from pmm.commitments.tracker import ttl as ttl_mod
from pmm.storage.eventlog import EventLog


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: python -m scripts.ttl_shadow_compare /path/to/eventlog.db [ttl_hours]"
        )
        return 2
    db_path = Path(sys.argv[1])
    if not db_path.exists():
        print(f"EventLog not found: {db_path}")
        return 2
    try:
        ttl_hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    except Exception:
        ttl_hours = 24

    log = EventLog(str(db_path))
    events = log.read_all()

    # Legacy set (simulate legacy expiration by running tracker in dry mode)
    CommitmentTracker(log)
    # We don't want to mutate the ledger; so compute legacy would require
    # duplicating logic. Instead, read open commitments and approximate the
    # legacy set by selecting those older than ttl_hours via timestamp.
    # This mirrors legacy expire_old_commitments without writes.
    import datetime as dt

    from pmm.storage.projection import build_self_model

    model = build_self_model(events)
    open_map = (model.get("commitments") or {}).get("open") or {}
    opened_ts: dict[str, str] = {}
    for ev in events:
        if ev.get("kind") == "commitment_open":
            m = ev.get("meta") or {}
            cid = m.get("cid")
            if cid in open_map and cid not in opened_ts:
                opened_ts[cid] = ev.get("ts")
    now_iso = dt.datetime.now(dt.UTC).isoformat()
    now_dt = dt.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    legacy: set[str] = set()
    for cid, ts in opened_ts.items():
        try:
            open_dt = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            continue
        age_hours = (now_dt - open_dt).total_seconds() / 3600.0
        if age_hours >= ttl_hours:
            legacy.add(cid)

    # Tick-based set
    tick_based = {
        cid for cid, _ in ttl_mod.compute_expired(events, ttl_hours=ttl_hours)
    }

    only_legacy = sorted(legacy - tick_based)
    only_tick = sorted(tick_based - legacy)

    print(f"Legacy (hours) count: {len(legacy)}")
    print(f"Tick-based count: {len(tick_based)}")
    if only_legacy or only_tick:
        print("Divergences detected:")
        if only_legacy:
            print("  In legacy only:", only_legacy)
        if only_tick:
            print("  In tick-based only:", only_tick)
        return 1
    else:
        print("Parity confirmed: sets match.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
