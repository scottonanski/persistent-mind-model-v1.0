"""Read-only Probe API.

Provides a simple snapshot of the current state derived from the event log
without performing any writes or external network calls.
"""

from __future__ import annotations

import argparse
import json
from typing import Dict

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model


def snapshot(eventlog: EventLog, *, limit: int = 50, redact=None) -> Dict:
    """Return a read-only state snapshot based on the current event log.

    Returns a dict of the shape:
      {
        "identity": {"name": str|None},
        "commitments": {"open": dict},
        "events": [ ... last <= limit events ... ]  # newest last
      }

    Notes:
      - Reads events via `eventlog.read_all()`
      - Builds the model via `build_self_model(events)`
      - `events` in the result are the last <= limit items (ascending order preserved)
    Optional redaction
    -------------------
    You can pass a redaction function via `redact` to transform each event just
    before returning. For example:

    def default_redactor(e):
        # Truncate large content
        if isinstance(e.get("content"), str) and len(e["content"]) > 2048:
            e = {**e, "content": e["content"][:2048] + "… (truncated)"}
        # Drop large blobs in meta
        meta = dict(e.get("meta") or {})
        if "blob" in meta:
            meta.pop("blob", None)
            e = {**e, "meta": meta}
        return e

    These helpers are examples only and not used by default.
    """
    events = eventlog.read_all()
    model = build_self_model(events)

    # Slice to last <= limit while keeping ascending order
    if limit and limit > 0:
        recent = events[-limit:]
    else:
        recent = events

    # Apply optional redaction to events just before returning
    events_out = [redact(e) for e in recent] if callable(redact) else recent

    return {
        "identity": model.get("identity", {"name": None}),
        "commitments": model.get("commitments", {"open": {}}),
        "events": events_out,
    }


def snapshot_paged(
    eventlog: EventLog,
    *,
    limit: int = 50,
    after_id: int | None = None,
    after_ts: str | None = None,
    redact=None,
) -> Dict:
    """
    Forward-paging snapshot. Returns same shape as `snapshot`, plus:
      - "next_after_id": int | None

    Semantics:
      - If after_id is provided, return events with id > after_id.
      - Else if after_ts is provided, return events with ts > after_ts.
      - Else, return the most recent <= limit events (ascending, newest last).

    Notes:
      - Always ascending order.
      - Strictly read-only; no writes.
    """
    # Build full model from all events (unchanged from snapshot())
    all_events = eventlog.read_all()
    model = build_self_model(all_events)

    # Determine page slice (ascending order)
    if after_id is not None:
        page = eventlog.read_after_id(after_id=after_id, limit=limit)
    elif after_ts is not None:
        page = eventlog.read_after_ts(after_ts=after_ts, limit=limit)
    else:
        # Start from the beginning when no cursor is provided for forward pagination
        page = eventlog.read_after_id(after_id=0, limit=limit)

    # Compute next_after_id if there are more rows beyond this page
    next_after_id: int | None = None
    if page:
        last_id = page[-1]["id"]
        more = eventlog.read_after_id(after_id=last_id, limit=1)
        if more:
            next_after_id = last_id

    # Apply optional redaction to events just before returning
    events_out = [redact(e) for e in page] if callable(redact) else page

    return {
        "identity": model.get("identity", {"name": None}),
        "commitments": model.get("commitments", {"open": {}}),
        "events": events_out,
        "next_after_id": next_after_id,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PMM Probe CLI (read-only)")
    parser.add_argument(
        "--db",
        required=True,
        help="Path to SQLite event log database (e.g., .data/pmm.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max number of recent events to include (ascending, newest last)",
    )

    args = parser.parse_args()

    evlog = EventLog(args.db)
    result = snapshot(evlog, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
