from __future__ import annotations

from typing import Dict, Optional, List

from pmm_v2.core.event_log import EventLog
from pmm_v2.core.ledger_mirror import LedgerMirror


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
    """Deterministically synthesize and append a reflection event.

    For user_turn: Uses the last user_message, assistant_message, and metrics_turn to compose
    a small, reproducible reflection payload.

    For autonomy_kernel: Reviews open commitments and synthesizes a commitment-focused reflection.

    Returns the new event id or None if prerequisites are missing (user_turn only).
    """
    if meta_extra and meta_extra.get("source") == "autonomy_kernel":
        # Autonomous commitment-review reflection – now with staleness detection and auto-close
        mirror = LedgerMirror(eventlog)
        open_cids = mirror.get_open_commitment_events()

        # Count events since the *oldest* open commitment
        oldest = min((c for c in open_cids), key=lambda c: c["id"], default=None)
        events_since = 0
        if oldest and staleness_threshold is not None:
            events_since = len(
                [e for e in eventlog.read_all() if e["id"] > oldest["id"]]
            )

        # Auto-close stale commitments
        if (
            auto_close_threshold is not None
            and events_since > auto_close_threshold
            and oldest
        ):
            eventlog.append(
                kind="commitment_close",
                content=f"CLOSE: {oldest['meta']['cid']}",
                meta={"reason": "auto_close_stale", "cid": oldest["meta"]["cid"]},
            )
            # Re-fetch open commitments after auto-close
            mirror = LedgerMirror(eventlog)
            open_cids = mirror.get_open_commitment_events()
            # Recalculate events_since based on new oldest
            oldest = min((c for c in open_cids), key=lambda c: c["id"], default=None)
            events_since = 0
            if oldest and staleness_threshold is not None:
                events_since = len(
                    [e for e in eventlog.read_all() if e["id"] > oldest["id"]]
                )

        stale_flag = 1 if events_since > staleness_threshold else 0

        should_cross_reference = len(open_cids) > 0

        content = (
            "{"
            f"commitments_reviewed:{len(open_cids)}"
            f",stale:{stale_flag}"
            f",relevance:'all_active'"
            f",action:'maintain'"
            f",next:'monitor'"
            "}"
        )
        if should_cross_reference:
            content += "\nREF: ../other_pmm_v2.db#47"
        meta = {
            "synth": "v2",
            "source": meta_extra.get("source") if meta_extra else "unknown",
        }
        meta.update(meta_extra or {})
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
            "{" f"intent:'{intent}'" f",outcome:'{outcome}'" f",next:'continue'" "}"
        )
        meta = {
            "synth": "v2",
            "source": meta_extra.get("source") if meta_extra else "unknown",
        }
        meta.update(meta_extra or {})
        return eventlog.append(kind="reflection", content=content, meta=meta)
