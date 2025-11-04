from __future__ import annotations

from typing import Dict, Optional, List

from pmm_v2.core.event_log import EventLog


def _last_by_kind(events: List[Dict], kind: str) -> Optional[Dict]:
    for e in reversed(events):
        if e.get("kind") == kind:
            return e
    return None


def synthesize_reflection(eventlog: EventLog, meta_extra: Optional[Dict[str, str]] = None, source: str = "user_turn") -> Optional[int]:
    """Deterministically synthesize and append a reflection event.

    For user_turn: Uses the last user_message, assistant_message, and metrics_turn to compose
    a small, reproducible reflection payload.

    For autonomy_kernel: Reviews open commitments and synthesizes a commitment-focused reflection.

    Returns the new event id or None if prerequisites are missing (user_turn only).
    """
    if source == "autonomy_kernel":
        from pmm_v2.core.ledger_mirror import LedgerMirror
        mirror = LedgerMirror(eventlog)
        open_cids = mirror.get_open_commitment_events()
        content = f"{{commitments_reviewed:{len(open_cids)},stale:0,relevance:'all_active',action:'maintain',next:'monitor'}}"
        meta = {"synth": "v2"}
        if meta_extra:
            meta.update(meta_extra)
        return eventlog.append(kind="reflection", content=content, meta=meta)
    else:
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
