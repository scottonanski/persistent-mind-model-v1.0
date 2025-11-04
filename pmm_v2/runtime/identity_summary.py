from __future__ import annotations

from typing import Dict, List, Optional

from pmm_v2.core.event_log import EventLog


def _events_since_last(events: List[Dict], kind: str) -> List[Dict]:
    idx = -1
    for i in range(len(events) - 1, -1, -1):
        if events[i].get("kind") == kind:
            idx = i
            break
    return events[(idx + 1) :] if idx != -1 else events


def maybe_append_summary(eventlog: EventLog) -> Optional[int]:
    """Append a deterministic identity summary when thresholds are met.

    Thresholds:
    - at least 3 reflections since last summary, OR
    - more than 10 events since last summary
    """
    events = eventlog.read_all()
    since = _events_since_last(events, "summary_update")
    reflections = [e for e in since if e.get("kind") == "reflection"]
    if len(reflections) < 3 and len(since) <= 10:
        return None

    # Derive open commitments deterministically: opens - closes
    opens = sum(1 for e in events if e.get("kind") == "commitment_open")
    closes = sum(1 for e in events if e.get("kind") == "commitment_close")
    open_commitments = max(0, opens - closes)

    # Observable ledger facts only (no psychometrics):
    reflections_since = len(reflections)
    last_event_id = events[-1]["id"] if events else 0

    content = (
        "{"
        f"open_commitments:{open_commitments}"
        f",reflections_since_last:{reflections_since}"
        f",last_event_id:{last_event_id}"
        "}"
    )
    return eventlog.append(kind="summary_update", content=content, meta={"synth": "v2"})
