# Path: pmm/core/ledger_metrics.py
"""Deterministic ledger metrics and self-consistency checks.

All computations are pure functions of the ledger rows. No heuristics,
no regex, no env-gated behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import time

from pmm.core.event_log import EventLog
from pmm.core.autonomy_tracker import AutonomyTracker
from pmm.core.commitment_manager import CommitmentManager
from pmm.core.ledger_mirror import LedgerMirror


def compute_metrics(
    db_path: str, tracker: Optional[AutonomyTracker] = None
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
    mirror = LedgerMirror(log, listen=False)
    kernel_knowledge_gaps = mirror.rsm_knowledge_gaps()

    # Replay speed metric (ms per event): reload + hash sequence
    t0 = time.perf_counter()
    _ = log.read_all()
    _ = log.hash_sequence()
    t1 = time.perf_counter()
    per_event_ms = ((t1 - t0) / max(1, len(raw_events))) * 1000.0

    metrics = {
        "event_count": len(canonical_events),
        "kinds": kinds,
        "broken_links": broken_links,
        "open_commitments": max(0, opens - closes),
        "closed_commitments": closes,
        "last_hash": last_hash,
        "internal_goals_open": internal_goals_open,
        "kernel_knowledge_gaps": kernel_knowledge_gaps,
        "replay_speed_ms": per_event_ms,
    }

    if tracker:
        tracker.rebuild()  # Ensure rebuild in case not done
        am = tracker.get_metrics()
        metrics["autonomy_metrics"] = {
            "ticks_total": am["ticks_total"],
            "reflect_count": am["reflect_count"],
            "summarize_count": am["summarize_count"],
            "intention_summarize_count": am.get("intention_summarize_count", 0),
            "idle_count": am["idle_count"],
            "last_reflection_id": am["last_reflection_id"],
            "open_commitments": am["open_commitments"],
        }

    return metrics


def format_metrics_human(metrics: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"event_count: {metrics['event_count']}")
    lines.append(f"broken_links: {metrics['broken_links']}")
    lines.append(f"open_commitments: {metrics['open_commitments']}")
    lines.append(f"closed_commitments: {metrics['closed_commitments']}")
    lines.append(f"last_hash: {metrics['last_hash']}")
    lines.append(f"replay_speed_ms: {metrics.get('replay_speed_ms', 0):.6f}")
    lines.append(f"Internal Goals Open: {metrics.get('internal_goals_open', 0)}")
    lines.append(f"Kernel knowledge gaps: {metrics.get('kernel_knowledge_gaps', 0)}")
    lines.append("kinds:")
    for k in sorted(metrics.get("kinds", {}).keys()):
        lines.append(f"  - {k}: {metrics['kinds'][k]}")
    if "autonomy_metrics" in metrics:
        am = metrics["autonomy_metrics"]
        lines.append("autonomy_metrics:")
        lines.append(f"  ticks_total: {am['ticks_total']}")
        lines.append(f"  reflect_count: {am['reflect_count']}")
        lines.append(f"  summarize_count: {am['summarize_count']}")
        lines.append(
            f"  intention_summarize_count: {am.get('intention_summarize_count', 0)}"
        )
        lines.append(f"  idle_count: {am['idle_count']}")
        lines.append(f"  last_reflection_id: {am['last_reflection_id']}")
        lines.append(f"  open_commitments: {am['open_commitments']}")
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
