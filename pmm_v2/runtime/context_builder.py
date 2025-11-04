from __future__ import annotations

from typing import List

from pmm_v2.core.event_log import EventLog


def build_context(eventlog: EventLog, limit: int = 5) -> str:
    """Deterministically reconstruct a short context window from the ledger.

    Includes only user/assistant messages, capped to the last `limit` pairs.
    """
    # Over-fetch recent events and then filter to message kinds
    rows = list(eventlog.read_tail(limit * 8))
    lines: List[str] = []
    for e in rows:
        kind = e.get("kind")
        if kind in ("user_message", "assistant_message"):
            lines.append(f"{kind}: {e.get('content','')}")
    tail = lines[-(limit * 2) :]
    return "\n".join(tail)
