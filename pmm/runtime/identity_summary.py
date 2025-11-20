# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/identity_summary.py
from __future__ import annotations

from typing import Dict, List, Optional
import json

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror


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
    # Derive open commitments via Mirror for canonical meta-based state
    mirror = Mirror(eventlog, enable_rsm=True, listen=False)
    open_commitments = len(mirror.get_open_commitment_events())

    # Observable ledger facts only (no psychometrics):
    reflections_since = len(reflections)
    last_event_id = events[-1]["id"] if events else 0

    current_snapshot = mirror.rsm_snapshot()

    last_summary = _last_summary_event(events)
    last_rsm_state = (
        (last_summary.get("meta") or {}).get("rsm_state") if last_summary else None
    )
    rsm_delta_info = _compute_rsm_trend(current_snapshot, last_rsm_state)
    threshold_reflections = len(reflections) >= 3
    threshold_events = len(since) > 10
    rsm_forced = False

    if last_summary is None:
        if not (threshold_reflections or threshold_events):
            return None
    else:
        if rsm_delta_info["significant"]:
            rsm_forced = True
        elif threshold_reflections:
            rsm_forced = False
        else:
            return None

    content_dict: Dict[str, object] = {
        "open_commitments": int(open_commitments),
        "reflections_since_last": int(reflections_since),
        "last_event_id": int(last_event_id),
    }
    if rsm_delta_info["description"]:
        content_dict["rsm_trend"] = rsm_delta_info["description"]
    if rsm_forced:
        content_dict["rsm_triggered"] = True
    content = json.dumps(content_dict, sort_keys=True, separators=(",", ":"))
    # Include full snapshot to preserve fast-rebuild parity
    meta = {"synth": "pmm", "rsm_state": current_snapshot}
    return eventlog.append(kind="summary_update", content=content, meta=meta)


def _last_summary_event(events: List[Dict]) -> Optional[Dict]:
    for event in reversed(events):
        if event.get("kind") == "summary_update":
            return event
    return None


def _compute_rsm_trend(
    current: Dict[str, object], previous: Optional[Dict[str, object]]
) -> Dict[str, object]:
    if not previous:
        return {"significant": False, "description": ""}

    tendencies_current = current.get("behavioral_tendencies", {}) or {}
    tendencies_previous = previous.get("behavioral_tendencies", {}) or {}
    gaps_current = set(current.get("knowledge_gaps", []) or [])
    gaps_previous = set(previous.get("knowledge_gaps", []) or [])

    deltas: Dict[str, int] = {}
    for key in sorted(set(tendencies_current) | set(tendencies_previous)):
        delta = tendencies_current.get(key, 0) - tendencies_previous.get(key, 0)
        if delta != 0:
            deltas[key] = delta

    significant = any(abs(value) > 10 for value in deltas.values()) or bool(
        gaps_current - gaps_previous
    )

    descriptions: List[str] = []
    for key in sorted(deltas):
        change = deltas[key]
        sign = "+" if change >= 0 else ""
        descriptions.append(f"{key} {sign}{change}")
    # Special phrasing for instantiation capacity when positive: "+N instantiation"
    inst_delta = deltas.get("instantiation_capacity")
    if isinstance(inst_delta, int) and inst_delta > 0:
        descriptions.append(f"+{inst_delta} instantiation")
    # Special phrasing for uniqueness emphasis when positive: "+N uniqueness"
    uniq_delta = deltas.get("uniqueness_emphasis")
    if isinstance(uniq_delta, int) and uniq_delta > 0:
        descriptions.append(f"+{uniq_delta} uniqueness")
    new_gaps = sorted(gaps_current - gaps_previous)
    if new_gaps:
        gap_str = ", ".join(new_gaps)
        descriptions.append(f"new gap: {gap_str}")

    return {
        "significant": significant,
        "description": ", ".join(descriptions) if descriptions else "",
    }
