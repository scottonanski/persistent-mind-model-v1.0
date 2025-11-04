"""Deterministic narration of existing ledger events (read-only)."""

from __future__ import annotations

from typing import List

from pmm_v2.core.event_log import EventLog


def narrate(ledger: EventLog, limit: int = 10) -> str:
    """Return a textual summary of the last N events.

    Format per line: [id] kind | content[:60]
    """
    events = ledger.read_tail(limit)
    lines: List[str] = []
    for ev in events:
        cid = ev.get("id")
        kind = ev.get("kind", "")
        content = (ev.get("content") or "")[:60]
        lines.append(f"[{cid}] {kind} | {content}")
    return "\n".join(lines)

