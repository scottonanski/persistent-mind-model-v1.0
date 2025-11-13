# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

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
from pmm.core.mirror import Mirror
from pmm.core.enhancements.stability_metrics import StabilityMetrics


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
    mirror = Mirror(log, enable_rsm=True, listen=False)
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

    meta_summaries = [event for event in canonical_events if event.get("kind") == "meta_summary"]
    stability = StabilityMetrics().compute(canonical_events, meta_summaries)
    metrics["stability"] = stability

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
    """Format metrics as simple text (for backward compatibility)."""
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


def format_metrics_tables(metrics: Dict[str, Any]):
    """Format metrics as Rich tables (returns table objects for direct printing)."""
    from rich.table import Table

    tables = []

    # Ledger Overview Table
    overview = Table(
        title="[bold cyan]Ledger Overview[/bold cyan]",
        show_header=True,
        header_style="bold",
    )
    overview.add_column("Metric", style="yellow", width=30)
    overview.add_column("Value", style="cyan")

    overview.add_row("Event Count", str(metrics["event_count"]))
    overview.add_row("Broken Links", str(metrics["broken_links"]))
    overview.add_row("Open Commitments", str(metrics["open_commitments"]))
    overview.add_row("Closed Commitments", str(metrics["closed_commitments"]))
    overview.add_row(
        "Replay Speed (ms/event)", f"{metrics.get('replay_speed_ms', 0):.6f}"
    )
    overview.add_row("Internal Goals Open", str(metrics.get("internal_goals_open", 0)))
    overview.add_row(
        "Kernel Knowledge Gaps", str(metrics.get("kernel_knowledge_gaps", 0))
    )
    overview.add_row("Last Hash", metrics["last_hash"][:16] + "...")

    tables.append(overview)

    # Event Kinds Table
    kinds_table = Table(
        title="[bold cyan]Event Kinds[/bold cyan]",
        show_header=True,
        header_style="bold",
    )
    kinds_table.add_column("Kind", style="yellow", width=30)
    kinds_table.add_column("Count", style="cyan", justify="right")

    for k in sorted(metrics.get("kinds", {}).keys()):
        kinds_table.add_row(k, str(metrics["kinds"][k]))

    tables.append(kinds_table)

    # Autonomy Metrics Table (if present)
    if "autonomy_metrics" in metrics:
        am = metrics["autonomy_metrics"]
        autonomy_table = Table(
            title="[bold cyan]Autonomy Metrics[/bold cyan]",
            show_header=True,
            header_style="bold",
        )
        autonomy_table.add_column("Metric", style="yellow", width=30)
        autonomy_table.add_column("Value", style="cyan", justify="right")

        autonomy_table.add_row("Ticks Total", str(am["ticks_total"]))
        autonomy_table.add_row("Reflect Count", str(am["reflect_count"]))
        autonomy_table.add_row("Summarize Count", str(am["summarize_count"]))
        autonomy_table.add_row(
            "Intention Summarize Count", str(am.get("intention_summarize_count", 0))
        )
        autonomy_table.add_row("Idle Count", str(am["idle_count"]))
        autonomy_table.add_row("Last Reflection ID", str(am["last_reflection_id"]))
        autonomy_table.add_row("Open Commitments", str(am["open_commitments"]))

        tables.append(autonomy_table)

    return tables


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
