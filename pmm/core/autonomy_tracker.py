# Path: pmm/core/autonomy_tracker.py
"""autonomy_tracker.py — deterministic, rebuildable autonomy telemetry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Optional

from pmm.core.event_log import EventLog


@dataclass
class _Counters:
    ticks_total: int = 0
    reflect_count: int = 0
    summarize_count: int = 0  # FACT: number of summary_update events
    intention_summarize_count: int = 0  # INTENT: ticks that chose summarize
    idle_count: int = 0
    last_reflection_id: Optional[int] = None


class AutonomyTracker:
    """Ledger-only, rebuildable autonomy telemetry. Emits every 10 ticks."""

    EMIT_EVERY_TICKS = 10

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self._counters = _Counters()
        self._last_emitted_tick_count = 0
        self._max_event_id = -1
        self.eventlog.register_listener(self.sync)

    def sync(self, event: Dict) -> None:
        kind = event.get("kind")
        meta = event.get("meta", {})

        if kind == "autonomy_tick":
            content = event.get("content", "{}")
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return
            decision = data.get("decision", "idle")
            self._counters.ticks_total += 1
            if decision == "reflect":
                self._counters.reflect_count += 1
            elif decision == "summarize":
                # Ledger-only truth for summarize_count: do not increment here.
                # Track intention separately for diagnostics.
                self._counters.intention_summarize_count += 1
            else:
                self._counters.idle_count += 1

        elif kind == "reflection" and meta.get("source") == "autonomy_kernel":
            self._counters.last_reflection_id = event["id"]
        elif kind == "summary_update":
            # Count actual summaries appended to the ledger as well.
            # This complements the autonomy_tick decision-based count,
            # ensuring the metric reflects real summary events even if
            # the decision wasn’t observed (e.g., during replays).
            self._counters.summarize_count += 1

        event_id = event.get("id", 0)
        if event_id > self._max_event_id:
            self._max_event_id = event_id
            self._maybe_emit()
        else:
            # For old events, just update counters without emitting
            pass

    def rebuild(self) -> None:
        self._counters = _Counters()
        self._last_emitted_tick_count = 0
        for ev in self.eventlog.read_all():
            self.sync(ev)

    def get_metrics(self) -> Dict[str, object]:
        events = self.eventlog.read_all()
        opened = sum(1 for e in events if e.get("kind") == "commitment_open")
        closed = sum(1 for e in events if e.get("kind") == "commitment_close")
        open_commits = max(0, opened - closed)

        return {
            "ticks_total": self._counters.ticks_total,
            "reflect_count": self._counters.reflect_count,
            "summarize_count": self._counters.summarize_count,
            "intention_summarize_count": self._counters.intention_summarize_count,
            "idle_count": self._counters.idle_count,
            "last_reflection_id": self._counters.last_reflection_id,
            "open_commitments": open_commits,
        }

    def should_emit(self) -> bool:
        return (
            self._counters.ticks_total > 0
            and self._counters.ticks_total % self.EMIT_EVERY_TICKS == 0
            and self._counters.ticks_total != self._last_emitted_tick_count
        )

    def _maybe_emit(self) -> None:
        if not self.should_emit():
            return
        self._last_emitted_tick_count = self._counters.ticks_total
        payload = json.dumps(self.get_metrics(), sort_keys=True, separators=(",", ":"))
        self.eventlog.append(
            kind="autonomy_metrics",
            content=payload,
            meta={"source": "autonomy_tracker"},
        )
