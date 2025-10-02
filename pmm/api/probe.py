"""Read-only Probe API.

Provides a simple snapshot of the current state derived from the event log
without performing any writes or external network calls.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from pmm.storage._shape import get_content_meta as _get_content_meta
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import (
    build_directives,
    build_directives_active_set,
    build_self_model,
)

# Tail scan windows (flag-less)
VIOLATIONS_TAIL_WINDOW = 500
COMMITMENTS_TAIL_WINDOW = 1000
DIRECTIVES_TAIL_WINDOW = 5000


def _tail(evlog: EventLog, n: int) -> list[dict[str, Any]]:
    """Best-effort tail reader with compatibility for fakes in tests."""
    if hasattr(evlog, "read_tail"):
        try:
            return list(evlog.read_tail(limit=int(n)))
        except TypeError:
            return list(evlog.read_tail(int(n)))
    # Fallback: full scan
    return list(evlog.read_all())


def snapshot(eventlog: EventLog, *, limit: int = 50, redact=None) -> dict:
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

    out = {
        "identity": model.get("identity", {"name": None}),
        "commitments": model.get("commitments", {"open": {}}),
        "events": events_out,
    }
    # Tiny augmentation: include top-k directives derived from the same events (read-only)
    try:
        dirs_all = build_directives(events)
        top = dirs_all[:5]
    except Exception:
        top = []
    out["directives"] = {"count": len(top), "top": top}
    return out


def snapshot_paged(
    eventlog: EventLog,
    *,
    limit: int = 50,
    after_id: int | None = None,
    after_ts: str | None = None,
    redact=None,
) -> dict:
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


# ---------- Directives helpers (pure; unit-testable) ----------


def snapshot_directives(evlog: EventLog, limit: int | None = None) -> list[dict]:
    """Return a stable list of directive records from the ledger (read-only)."""
    # Use a large tail window to avoid full scans while remaining deterministic
    events = _tail(evlog, DIRECTIVES_TAIL_WINDOW)
    view = build_directives(events)
    return view if limit is None else view[: max(0, int(limit))]


def render_directives(rows: list[dict]) -> str:
    """Pretty-print directives deterministically in a compact table-like layout."""
    lines: list[str] = []
    lines.append("idx | seen | sources            | first_id | last_id | content")
    lines.append(
        "----+------+--------------------+----------+---------+--------------------------------"
    )
    for i, r in enumerate(rows, start=1):
        sources = ",".join(r.get("sources", []))
        first_id = (
            int(r.get("first_seen_id", 0))
            if "first_seen_id" in r
            else int(r.get("first_seen_id", 0))
        )
        last_id = (
            int(r.get("last_seen_id", 0))
            if "last_seen_id" in r
            else int(r.get("last_seen_id", 0))
        )
        lines.append(
            f"{i:>3} | {int(r.get('seen_count', 0)):>4} | {sources:<18} | "
            f"{first_id:>8} | {last_id:>7} | {r.get('content', '')}"
        )
    return "\n".join(lines)


# ---------- Directives active set (read-only) ----------


def snapshot_directives_active(evlog: EventLog, top_k: int | None = None) -> list[dict]:
    ev = _tail(evlog, DIRECTIVES_TAIL_WINDOW)
    rows = build_directives_active_set(ev)
    return rows if top_k is None else rows[: max(0, int(top_k))]


def render_directives_active(rows: list[dict]) -> str:
    lines: list[str] = []
    lines.append("idx | score | seen | recent | first_id | last_id | content")
    lines.append(
        "----+-------+------+--------+----------+---------+------------------------------"
    )
    for i, r in enumerate(rows, start=1):
        lines.append(
            f"{i:>3} | {r['score']:>5.1f} | {int(r.get('seen_count') or 0):>4} | {int(r.get('recent_hits') or 0):>6} | "
            f"{int(r.get('first_seen_id') or 0):>8} | {int(r.get('last_seen_id') or 0):>7} | {r.get('content', '')}"
        )
    return "\n".join(lines)


def enrich_snapshot_with_directives(
    snapshot: dict, evlog: EventLog, top_k: int = 5
) -> dict:
    """Augment an existing snapshot dict with a 'directives' section (top-k only)."""
    try:
        top = snapshot_directives(evlog, limit=top_k)
    except Exception:
        top = []
    snap = dict(snapshot or {})
    snap["directives"] = {"count": len(top), "top": top}
    return snap


# ---------- Invariants violations (read-only) ----------


def snapshot_violations(evlog: EventLog, limit: int | None = None) -> list[dict]:
    """Return recent invariant_violation events (most-recent first), read-only."""
    tail_n = max(int(limit or 20), VIOLATIONS_TAIL_WINDOW)
    events = _tail(evlog, tail_n)
    rows: list[dict] = []
    for ev in reversed(events):  # newest first
        if ev.get("kind") != "invariant_violation":
            continue
        pay = ev.get("payload") or {}
        meta = ev.get("meta") or {}
        rows.append(
            {
                "ts": ev.get("ts") or ev.get("timestamp"),
                "id": ev.get("id"),
                "code": pay.get("code") or meta.get("code"),
                "message": pay.get("message") or meta.get("message") or "",
                "details": pay.get("details") or meta.get("details") or {},
            }
        )
        if limit is not None and len(rows) >= int(limit):
            break
    return rows


def render_violations(rows: list[dict]) -> str:
    """Deterministic, minimal table render for invariant violations."""
    lines: list[str] = []
    lines.append(
        "idx | code                     | ts                | id     | message"
    )
    lines.append(
        "----+--------------------------+-------------------+--------+---------------------------"
    )
    for i, r in enumerate(rows, start=1):
        code = str(r.get("code") or "")[:24]
        ts = str(r.get("ts") or "")
        rid = str(r.get("id") or "")
        msg = str(r.get("message") or "")
        lines.append(f"{i:>3} | {code:<24} | {ts:<17} | {rid:<6} | {msg}")
    return "\n".join(lines)


# ---------- Open commitments (read-only) ----------


def snapshot_commitments_open(
    evlog: EventLog, limit: int | None = None
) -> list[dict[str, Any]]:
    """
    Return newest-first list of currently open commitments.
    Deterministic rules:
      - Traverse events newest->oldest.
      - Maintain sets of seen closures by cid and by normalized text.
      - Include an open only if neither its cid nor its text has been seen closed yet.
      - De-dup by cid if present, else by normalized text.
    Tolerates payload/content variants.
    """
    tail_n = max(int(limit or 20), COMMITMENTS_TAIL_WINDOW)
    events = _tail(evlog, tail_n)

    def _norm_text(s: str) -> str:
        return " ".join((s or "").split()).strip().rstrip(";,")

    def _extract_text(ev: dict[str, Any]) -> str:
        content, meta = _get_content_meta(ev)
        # Prefer explicit meta.text if present, else strip known prefixes from content
        text = meta.get("text")
        if text:
            return str(text)
        if isinstance(content, str):
            for pref in ("Commitment opened:", "Commitment closed:"):
                if content.startswith(pref):
                    return content.split(":", 1)[-1].strip()
        return content

    closed_cids: set[str] = set()
    closed_texts: set[str] = set()
    included_keys: set[str] = set()
    opens: list[dict[str, Any]] = []

    for ev in reversed(events):
        k = ev.get("kind")
        if k == "commitment_close":
            m = ev.get("meta") or {}
            cid = m.get("cid")
            if cid:
                closed_cids.add(str(cid))
            ntext = _norm_text(_extract_text(ev))
            if ntext:
                closed_texts.add(ntext)
            continue
        if k != "commitment_open":
            continue
        meta = ev.get("meta") or {}
        cid = meta.get("cid")
        ntext = _norm_text(_extract_text(ev))
        # skip empty
        if not cid and not ntext:
            continue
        # closed check (by cid or text)
        if (cid and str(cid) in closed_cids) or (ntext and ntext in closed_texts):
            continue
        # de-dup: prefer cid key when present, else text key
        key = str(cid) if cid else f"txt::{ntext}"
        if key in included_keys:
            continue
        included_keys.add(key)
        opens.append(
            {
                "id": ev.get("id"),
                "ts": ev.get("ts") or ev.get("timestamp"),
                "cid": str(cid) if cid else "",
                "content": ntext,
                "origin_eid": meta.get("origin_eid")
                or ((ev.get("payload") or {}).get("meta") or {}).get("origin_eid"),
            }
        )
        if limit is not None and len(opens) >= int(limit):
            break
    return opens


def render_commitments_open(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append(
        "idx | ts                | id     | origin_eid | cid                           | content"
    )
    lines.append(
        "----+-------------------+--------+------------+-------------------------------+------------------------------"
    )
    for i, r in enumerate(rows, start=1):
        ts = str(r.get("ts") or "")
        rid = str(r.get("id") or "")
        oe = str(r.get("origin_eid") or "")
        cid = str(r.get("cid") or "")
        content = r.get("content") or ""
        lines.append(f"{i:>3} | {ts:<17} | {rid:<6} | {oe:<10} | {cid:<29} | {content}")
    return "\n".join(lines)


# ---------- Memory summary (read-only) ----------


def memory_summary(evlog: EventLog) -> str:
    """Return a compact human-readable summary of persistent state.

    Includes identity, a short list of open commitments, and a count of
    reflections and directives. Purely read-only.
    """
    events = evlog.read_all()
    model = build_self_model(events)
    name = (model.get("identity") or {}).get("name") or "—"
    # Open commitments (top 3 by recency)
    opens = []
    seen = set()
    for ev in reversed(events):
        if ev.get("kind") != "commitment_open":
            continue
        m = ev.get("meta") or {}
        cid = str(m.get("cid") or "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        text = str(m.get("text") or "").strip()
        if text:
            # First non-empty line, truncated
            line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
            opens.append(line[:80])
        if len(opens) >= 3:
            break
    refl_count = sum(1 for e in events if e.get("kind") == "reflection")
    dirs = build_directives(events)
    lines: list[str] = []
    lines.append(f"Identity: {name}")
    if opens:
        lines.append("Open commitments:")
        for t in opens:
            lines.append(f"- {t}")
    lines.append(f"Reflections: {refl_count}")
    lines.append(f"Directives: {len(dirs)}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PMM Probe CLI (read-only)")
    # Backward-compatible flags (no subcommand): default prints snapshot JSON
    parser.add_argument(
        "--db", required=False, help="Path to SQLite event log database"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max number of recent events to include (ascending, newest last)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Top-K directives to include in snapshot augmentation",
    )

    sub = parser.add_subparsers(dest="cmd")

    # directives subcommand (table output)
    p_dir = sub.add_parser(
        "directives", help="List ledger-native autonomy directives (read-only)"
    )
    p_dir.add_argument("--db", required=False, help="Path to SQLite event log database")
    p_dir.add_argument("--limit", type=int, default=None, help="Max rows to display")

    # snapshot subcommand (explicit; prints JSON)
    p_snap = sub.add_parser("snapshot", help="Show read-only PMM snapshot (JSON)")
    p_snap.add_argument(
        "--db", required=False, help="Path to SQLite event log database"
    )
    p_snap.add_argument(
        "--limit", type=int, default=50, help="Max number of recent events"
    )
    p_snap.add_argument(
        "--top-k", type=int, default=5, help="Top-K directives to include"
    )

    # violations subcommand (table output)
    p_v = sub.add_parser(
        "violations", help="List recent invariant violations (read-only)"
    )
    p_v.add_argument("--db", required=False, help="Path to SQLite event log database")
    p_v.add_argument(
        "--limit", type=int, default=20, help="Max rows to display (newest first)"
    )

    # directives-active subcommand (table output)
    p_da = sub.add_parser(
        "directives-active", help="Show active directives (read-only)"
    )
    p_da.add_argument("--db", required=False, help="Path to SQLite event log database")
    p_da.add_argument("--top-k", type=int, default=7)

    # commitments-open subcommand (table output)
    p_co = sub.add_parser(
        "commitments-open", help="List currently open commitments (read-only)"
    )
    p_co.add_argument("--db", required=False, help="Path to SQLite event log database")
    p_co.add_argument(
        "--limit", type=int, default=20, help="Max rows to display (newest first)"
    )

    # memory-summary subcommand (compact text output)
    p_ms = sub.add_parser(
        "memory-summary", help="Print a compact memory summary (read-only)"
    )
    p_ms.add_argument("--db", required=False, help="Path to SQLite event log database")

    args = parser.parse_args()

    if args.cmd == "directives":
        evlog = EventLog(args.db) if getattr(args, "db", None) else EventLog()
        rows = snapshot_directives(evlog, limit=args.limit)
        print(render_directives(rows))
    elif args.cmd == "snapshot":
        evlog = EventLog(args.db) if getattr(args, "db", None) else EventLog()
        res = snapshot(evlog, limit=args.limit)
        # Ensure directives top-k follows the subcommand's arg
        res = enrich_snapshot_with_directives(res, evlog, top_k=args.top_k)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "violations":
        evlog = EventLog(args.db) if getattr(args, "db", None) else EventLog()
        rows = snapshot_violations(evlog, limit=args.limit)
        print(render_violations(rows))
    elif args.cmd == "directives-active":
        evlog = EventLog(args.db) if getattr(args, "db", None) else EventLog()
        rows = snapshot_directives_active(evlog, top_k=args.top_k)
        print(render_directives_active(rows))
    elif args.cmd == "commitments-open":
        evlog = EventLog(args.db) if getattr(args, "db", None) else EventLog()
        rows = snapshot_commitments_open(evlog, limit=args.limit)
        print(render_commitments_open(rows))
    elif args.cmd == "memory-summary":
        evlog = EventLog(args.db) if getattr(args, "db", None) else EventLog()
        print(memory_summary(evlog))
    else:
        # Backward-compatible default: behave like original CLI (print snapshot JSON)
        evlog = EventLog(args.db) if getattr(args, "db", None) else EventLog()
        res = snapshot(evlog, limit=args.limit)
        print(json.dumps(res, ensure_ascii=False, indent=2))
