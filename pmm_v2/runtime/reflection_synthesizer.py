from __future__ import annotations

from typing import Dict, Optional, List
import json

from pmm_v2.core.event_log import EventLog


def _last_by_kind(events: List[Dict], kind: str) -> Optional[Dict]:
    for e in reversed(events):
        if e.get("kind") == kind:
            return e
    return None


def synthesize_reflection(
    eventlog: EventLog,
    meta_extra: Optional[Dict[str, str]] = None,
    source: str = "user_turn",
    staleness_threshold: Optional[int] = None,
    auto_close_threshold: Optional[int] = None,
) -> Optional[int]:
    if meta_extra and meta_extra.get("source") == "autonomy_kernel":
        from pmm_v2.runtime.autonomy_kernel import AutonomyKernel

        autonomy = AutonomyKernel(eventlog)
        return autonomy.reflect(
            eventlog, meta_extra, staleness_threshold, auto_close_threshold
        )
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
        content = json.dumps(
            {"intent": intent, "outcome": outcome, "next": "continue"},
            sort_keys=True,
            separators=(",", ":"),
        )
        meta = {
            "synth": "v2",
            "source": meta_extra.get("source") if meta_extra else "unknown",
        }
        meta.update(meta_extra or {})
        return eventlog.append(kind="reflection", content=content, meta=meta)
