"""Deterministic ledger metrics and self-consistency checks.

All computations are pure functions of the ledger rows. No heuristics,
no regex, no env-gated behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pmm_v2.core.event_log import EventLog
from pmm_v2.core.autonomy_tracker import AutonomyTracker
from pmm_v2.core.commitment_manager import CommitmentManager


def compute_metrics(
    db_path: str, tracker: Optional[AutonomyTracker] = None, rsm: Optional[Any] = None
) -> Dict[str, Any]:
    """Compute deterministic metrics and integrity info for a ledger.

    Returns dict with keys:
      - event_count
      - kinds: per-kind counts
      - broken_links: count of prev_hash discontinuities
      - last_hash: last event hash or "0"*64 if empty
      - open_commitments: number of currently open commitments
      - closed_commitments: number of commitment_close events
    """
    log = EventLog(db_path)
    raw_events = log.read_all()
    instrumentation: set[str] = {"metrics_update"}

    prev_hash: Optional[str] = None
    broken_links = 0
    for event in raw_events:
        ph = event.get("prev_hash")
        if prev_hash is None:
            if ph not in (
                None,
                "",
            ):
                broken_links += 1
        else:
            if ph != prev_hash:
                broken_links += 1
        prev_hash = event.get("hash")

    canonical_events = [
        event for event in raw_events if event.get("kind") not in instrumentation
    ]

    kinds: Dict[str, int] = {}
    opens = 0
    closes = 0
    for event in canonical_events:
        kind = event.get("kind")
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "commitment_open":
            opens += 1
        elif kind == "commitment_close":
            closes += 1

    if canonical_events:
        last_hash = canonical_events[-1]["hash"]
    else:
        last_hash = "0" * 64

    manager = CommitmentManager(log)
    internal_goals_open = len(manager.get_open_commitments(origin="autonomy_kernel"))

    metrics = {
        "event_count": len(canonical_events),
        "kinds": kinds,
        "broken_links": broken_links,
        "open_commitments": max(0, opens - closes),
        "closed_commitments": closes,
        "last_hash": last_hash,
        "internal_goals_open": internal_goals_open,
    }

    if tracker:
        tracker.rebuild()  # Ensure rebuild in case not done
        am = tracker.get_metrics()
        metrics["autonomy_metrics"] = {
            "ticks_total": am["ticks_total"],
            "reflect_count": am["reflect_count"],
            "summarize_count": am["summarize_count"],
            "idle_count": am["idle_count"],
            "last_reflection_id": am["last_reflection_id"],
            "open_commitments": am["open_commitments"],
        }

    if rsm:
        rsm.rebuild()
        metrics["rsm"] = rsm.get_snapshot()

    return metrics


def format_metrics_human(metrics: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"event_count: {metrics['event_count']}")
    lines.append(f"broken_links: {metrics['broken_links']}")
    lines.append(f"open_commitments: {metrics['open_commitments']}")
    lines.append(f"closed_commitments: {metrics['closed_commitments']}")
    lines.append(f"last_hash: {metrics['last_hash']}")
    lines.append(f"Internal Goals Open: {metrics.get('internal_goals_open', 0)}")
    lines.append("kinds:")
    for k in sorted(metrics.get("kinds", {}).keys()):
        lines.append(f"  - {k}: {metrics['kinds'][k]}")
    if "autonomy_metrics" in metrics:
        am = metrics["autonomy_metrics"]
        lines.append("autonomy_metrics:")
        lines.append(f"  ticks_total: {am['ticks_total']}")
        lines.append(f"  reflect_count: {am['reflect_count']}")
        lines.append(f"  summarize_count: {am['summarize_count']}")
        lines.append(f"  idle_count: {am['idle_count']}")
        lines.append(f"  last_reflection_id: {am['last_reflection_id']}")
        lines.append(f"  open_commitments: {am['open_commitments']}")
    if "rsm" in metrics:
        rsm = metrics["rsm"]
        lines.append("rsm:")
        lines.append(f"  reflections: {rsm.get('reflections', 0)}")
        lines.append(f"  commitments: {rsm.get('commitments', 0)}")
        lines.append(f"  gaps: {rsm.get('gaps', 0)}")
        intents = rsm.get("intents", {})
        if intents:
            lines.append("  intents:")
            for k in sorted(intents.keys()):
                lines.append(f"    {k}: {intents[k]}")
    return "\n".join(lines)


def _last_metrics_snapshot(events: List[Dict[str, Any]]) -> Optional[str]:
    last: Optional[str] = None
    for e in events:
        if e.get("kind") == "metrics_update":
            last = e.get("content")
    return last


def _stable_serialize_snapshot(d: Dict[str, Any]) -> str:
    kinds_items = ",".join(
        f"{k}:{d['kinds'][k]}" for k in sorted(d.get("kinds", {}).keys())
    )
    return (
        f"{{"
        f"event_count:{d['event_count']},"
        f"kinds:{{{kinds_items}}},"
        f"broken_links:{d['broken_links']},"
        f"open_commitments:{d['open_commitments']},"
        f"closed_commitments:{d['closed_commitments']},"
        f"last_hash:{d['last_hash']}"
        f"}}"
    )


def append_metrics_if_delta(db_path: str) -> bool:
    """Append a metrics_update event only if computed snapshot differs from last one.

    Returns True if appended, False if no-op.
    """
    log = EventLog(db_path)
    events = log.read_all()
    new_metrics = compute_metrics(db_path)
    new_snapshot = _stable_serialize_snapshot(new_metrics)
    last_snapshot = _last_metrics_snapshot(events)
    if last_snapshot == new_snapshot:
        return False
    log.append(kind="metrics_update", content=new_snapshot, meta={})
    return True
