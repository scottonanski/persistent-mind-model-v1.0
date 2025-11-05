"""Deterministic narration of existing ledger events (read-only)."""

from __future__ import annotations

from typing import List
import json

from pmm_v2.core.event_log import EventLog


def narrate(ledger: EventLog, limit: int = 10) -> str:
    """Return a textual summary of the last N events.

    Format per line: [id] kind | content | meta_str
    """
    events = ledger.read_tail(limit)
    lines: List[str] = []
    for ev in events:
        cid = ev.get("id")
        kind = ev.get("kind", "")
        content = ev.get("content") or ""
        meta = ev.get("meta")
        meta_str = f"meta:{json.dumps(meta, separators=(',', ':'))}" if meta else ""
        lines.append(f"[{cid}] {kind} | {content} | {meta_str}")
    return "\n".join(lines)
