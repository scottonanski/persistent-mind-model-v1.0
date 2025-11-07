"""Deterministic narration of existing ledger events (read-only)."""

from __future__ import annotations

from typing import List
import json

from pmm.core.event_log import EventLog


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
        suffix = ""
        if kind == "inter_ledger_ref":
            verified = (meta or {}).get("verified")
            if verified is False:
                suffix = f" (unverified ref: {content} - create dummy for test)"
        lines.append(f"[{cid}] {kind} | {content} | {meta_str}{suffix}")
    return "\n".join(lines)
