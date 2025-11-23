# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/reflection_synthesizer.py
from __future__ import annotations

from typing import Any, Dict, Optional, List, Tuple, TYPE_CHECKING
import json

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.core.commitment_manager import CommitmentManager
from pmm.core.enhancements.meta_reflection_engine import MetaReflectionEngine

if TYPE_CHECKING:
    from pmm.runtime.autonomy_kernel import AutonomyKernel


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
    autonomy: "AutonomyKernel" | None = None,
    mirror: Mirror | None = None,
) -> Optional[int]:
    if meta_extra and meta_extra.get("source") == "autonomy_kernel":
        if autonomy is None:
            from pmm.runtime.autonomy_kernel import AutonomyKernel

            autonomy = AutonomyKernel(eventlog)
        return autonomy.reflect(
            eventlog, meta_extra, staleness_threshold, auto_close_threshold
        )
    else:
        events = eventlog.read_tail(limit=500)
        user = _last_by_kind(events, "user_message")
        assistant = _last_by_kind(events, "assistant_message")
        metrics = _last_by_kind(events, "metrics_turn")
        if not (user and assistant and metrics):
            return None

        intent = (user.get("content") or "").strip()[:256]
        outcome = (assistant.get("content") or "").strip()[:256]
        payload = {"intent": intent, "outcome": outcome, "next": "continue"}

        if mirror is not None:
            internal = [
                e
                for e in mirror.get_open_commitment_events()
                if (e.get("meta") or {}).get("origin") == "autonomy_kernel"
            ]
        else:
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
            mirror = Mirror(eventlog, enable_rsm=True, listen=False)
            snapshot = mirror.rsm_snapshot()

            # Add graph structure awareness
            from pmm.core.meme_graph import MemeGraph

            mg = MemeGraph(eventlog)
            mg.rebuild(events)
            stats = mg.graph_stats()

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

                # Include graph density if meaningful (>= 5 nodes)
                if stats["nodes"] >= 5:
                    density = f"{stats['edges']}/{stats['nodes']}"
                    description += f", graph: {density}"

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
        reflection_id = eventlog.append(kind="reflection", content=content, meta=meta)
        summary = None
        try:
            if all("id" in ev for ev in events):
                summary = MetaReflectionEngine(eventlog).generate()
        except Exception:
            summary = None
        if summary is not None:
            eventlog.append(
                kind="meta_summary",
                content=json.dumps(summary, sort_keys=True, separators=(",", ":")),
                meta={
                    "source": "meta_reflection_engine",
                    "about_event": reflection_id,
                },
            )
        return reflection_id


def _has_rsm_data(snapshot: Dict[str, Any]) -> bool:
    if not snapshot:
        return False
    tendencies = snapshot.get("behavioral_tendencies") or {}
    gaps = snapshot.get("knowledge_gaps") or []
    meta_patterns = snapshot.get("interaction_meta_patterns") or []
    return bool(tendencies or gaps or meta_patterns)


def synthesize_kernel_reflection(
    ledger_slice: List[Dict[str, Any]], *, staleness_threshold: int = 20
) -> Optional[Tuple[Dict[str, Any], str]]:
    """Deterministically synthesize autonomy_kernel reflection payload.

    Returns (payload, delta_hash) or None if the computed delta_hash matches the
    last autonomy_kernel reflection in the provided slice. This provides a
    lightweight skip mechanism without requiring full-ledger context.
    """
    import hashlib as _hl

    # Compute delta hash over last 3 NON-reflection events in the slice
    non_ref = [e for e in ledger_slice if e.get("kind") != "reflection"]
    slice3 = non_ref[-3:]
    compact = [
        {
            "kind": e.get("kind"),
            "content": e.get("content"),
            "meta": e.get("meta"),
        }
        for e in slice3
    ]
    delta_hash = _hl.sha256(
        json.dumps(compact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    # If the last autonomy_kernel reflection in the slice carries the same hash, skip
    last_ref = None
    last_ref_index = -1
    for idx in range(len(ledger_slice) - 1, -1, -1):
        e = ledger_slice[idx]
        if (
            e.get("kind") == "reflection"
            and (e.get("meta") or {}).get("source") == "autonomy_kernel"
        ):
            last_ref = e
            last_ref_index = idx
            break
    last_delta = (last_ref.get("meta") or {}).get("delta_hash") if last_ref else None
    # If there were no new non-ref events after the last autonomy reflection, skip
    if last_ref is not None:
        if not any(
            (ev.get("kind") != "reflection")
            for ev in ledger_slice[last_ref_index + 1 :]
        ):
            return None
    # If hashes match (when computable), skip
    if last_delta and last_delta == delta_hash:
        return None

    # Build content from slice facts
    open_commitments = [e for e in ledger_slice if e.get("kind") == "commitment_open"]
    oldest = min(open_commitments, key=lambda e: e.get("id", 0), default=None)
    events_since = 0
    if oldest is not None:
        events_since = sum(
            1 for e in ledger_slice if int(e.get("id", 0)) > int(oldest.get("id", 0))
        )
    stale_flag = 1 if (oldest is not None and events_since > staleness_threshold) else 0

    # Dominant kind heuristic from slice
    kinds = {}
    for e in ledger_slice:
        k = e.get("kind")
        kinds[k] = kinds.get(k, 0) + 1
    dominant_kind = max(kinds, key=kinds.get) if kinds else "unknown"

    payload: Dict[str, Any] = {
        "intent": f"{dominant_kind}_analysis",
        "outcome": f"{len(open_commitments)} open, stale={stale_flag}",
        "next": "monitor",
        "commitments_reviewed": len(open_commitments),
        "stale": stale_flag,
        "relevance": "all_active",
        "action": "maintain",
    }

    # Inject ontological meditation periodically
    total_events = len(ledger_slice)
    if total_events > 50 and total_events % 47 == 0:  # Every 47 events after 50
        from pmm.runtime.prompts import get_ontological_meditation

        meditation_index = (total_events // 47) % 11
        meditation = get_ontological_meditation(meditation_index)
        if meditation:
            payload["ontological_inquiry"] = meditation

    return payload, delta_hash
