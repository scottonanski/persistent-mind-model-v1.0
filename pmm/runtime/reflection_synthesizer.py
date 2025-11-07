# Path: pmm/runtime/reflection_synthesizer.py
from __future__ import annotations

from typing import Any, Dict, Optional, List
import json

from pmm.core.event_log import EventLog
from pmm.core.ledger_mirror import LedgerMirror
from pmm.core.commitment_manager import CommitmentManager


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
        from pmm.runtime.autonomy_kernel import AutonomyKernel

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
        payload = {"intent": intent, "outcome": outcome, "next": "continue"}

        internal = CommitmentManager(eventlog).get_open_commitments(
            origin="autonomy_kernel"
        )
        if internal:
            payload["internal_goals"] = [
                f"{c.get('meta', {}).get('cid')} ({c.get('meta', {}).get('goal')})"
                for c in internal
            ]

        reflection_count = sum(1 for e in events if e.get("kind") == "reflection")
        if reflection_count >= 5:
            mirror = LedgerMirror(eventlog, listen=False)
            snapshot = mirror.rsm_snapshot()
            if _has_rsm_data(snapshot):
                det_refs = snapshot["behavioral_tendencies"].get(
                    "determinism_emphasis", 0
                )
                gaps = snapshot["knowledge_gaps"]
                gap_count = len(gaps)
                description = (
                    f"RSM: {det_refs} determinism refs, {gap_count} knowledge gaps"
                )
                if gaps:
                    description += f" ({', '.join(gaps)})"
                payload["self_model"] = description

        content = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        meta = {
            "synth": "pmm",
            "source": meta_extra.get("source") if meta_extra else "unknown",
        }
        meta.update(meta_extra or {})
        return eventlog.append(kind="reflection", content=content, meta=meta)


def _has_rsm_data(snapshot: Dict[str, Any]) -> bool:
    if not snapshot:
        return False
    tendencies = snapshot.get("behavioral_tendencies") or {}
    gaps = snapshot.get("knowledge_gaps") or []
    meta_patterns = snapshot.get("interaction_meta_patterns") or []
    return bool(tendencies or gaps or meta_patterns)
