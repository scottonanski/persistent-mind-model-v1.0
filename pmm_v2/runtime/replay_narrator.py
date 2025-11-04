"""Deterministic narration of existing ledger events (read-only)."""

from __future__ import annotations

from typing import List

from pmm_v2.core.event_log import EventLog


def narrate(ledger: EventLog, limit: int = 10) -> str:
    """Return a textual summary of the last N events.

    Format per line: [id] timestamp kind | content[:60]
    For inter_ledger_ref: [id] timestamp inter_ledger_ref | ✓/✗ content
    """
    events = ledger.read_tail(limit)
    lines: List[str] = []
    for ev in events:
        cid = ev.get("id")
        ts = ev.get("ts", "")
        kind = ev.get("kind", "")
        content = (ev.get("content") or "")[:60]
        if kind == "inter_ledger_ref":
            meta = ev.get("meta", {})
            status = "✓" if meta.get("verified") else "✗"
            lines.append(f"[{cid}] {ts} {kind} | {status} {content}")
        else:
            lines.append(f"[{cid}] {ts} {kind} | {content}")
    return "\n".join(lines)
