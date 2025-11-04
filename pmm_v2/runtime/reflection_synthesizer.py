from __future__ import annotations

from typing import Dict, Optional, List

from pmm_v2.core.event_log import EventLog


def _last_by_kind(events: List[Dict], kind: str) -> Optional[Dict]:
    for e in reversed(events):
        if e.get("kind") == kind:
            return e
    return None


def synthesize_reflection(eventlog: EventLog, meta_extra: Optional[Dict[str, str]] = None) -> Optional[int]:
    """Deterministically synthesize and append a reflection event.

    Uses the last user_message, assistant_message, and metrics_turn to compose
    a small, reproducible reflection payload. Returns the new event id or None
    if prerequisites are missing.
    """
    events = eventlog.read_all()
    user = _last_by_kind(events, "user_message")
    assistant = _last_by_kind(events, "assistant_message")
    metrics = _last_by_kind(events, "metrics_turn")
    if not (user and assistant and metrics):
        return None

    intent = (user.get("content") or "").strip()[:256]
    outcome = (assistant.get("content") or "").strip()[:256]
    # Compose a stable, manually-ordered string (no json.dumps ordering)
    content = (
        "{"
        f"intent:'{intent}'"
        f",outcome:'{outcome}'"
        f",next:'continue'"
        "}"
    )
    meta = {"synth": "v2"}
    if meta_extra:
        meta.update(meta_extra)
    return eventlog.append(kind="reflection", content=content, meta=meta)
