from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from pmm_v2.core.event_log import EventLog


def _last_event(events: List[Dict], kind: str) -> Optional[Dict]:
    for event in reversed(events):
        if event.get("kind") == kind:
            return event
    return None


def _events_after(events: List[Dict], anchor: Optional[Dict]) -> List[Dict]:
    if anchor is None:
        return events
    anchor_id = anchor.get("id", 0)
    return [event for event in events if event.get("id", 0) > anchor_id]


def _last_event_matching(
    events: List[Dict], kind: str, predicate: Callable[[Dict], bool]
) -> Optional[Dict]:
    for event in reversed(events):
        if event.get("kind") == kind and predicate(event):
            return event
    return None


@dataclass(frozen=True)
class KernelDecision:
    decision: str
    reasoning: str
    evidence: List[int]

    def as_dict(self) -> Dict[str, object]:
        return {
            "decision": self.decision,
            "reasoning": self.reasoning,
            "evidence": list(self.evidence),
        }


class AutonomyKernel:
    """Deterministic self-direction derived solely from ledger facts."""

    def __init__(
        self, eventlog: EventLog, thresholds: Optional[Dict[str, int]] = None
    ) -> None:
        self.eventlog = eventlog
        defaults = {
            "reflection_interval": 10,
            "summary_interval": 50,
            "commitment_staleness": 20,
            "commitment_auto_close": 27,
        }
        self.thresholds = defaults.copy()
        if thresholds:
            for key, value in thresholds.items():
                if key in self.thresholds:
                    self.thresholds[key] = int(value)

    def ensure_rule_table_event(self) -> None:
        """Record the kernel's rule table in the ledger exactly once."""
        content = (
            "{"
            f"reflection_interval:{self.thresholds['reflection_interval']}"
            f",summary_interval:{self.thresholds['summary_interval']}"
            f",commitment_staleness:{self.thresholds['commitment_staleness']}"
            f",commitment_auto_close:{self.thresholds['commitment_auto_close']}"
            "}"
        )
        self.eventlog.append(
            kind="autonomy_rule_table",
            content=content,
            meta={"source": "autonomy_kernel"},
        )

    def reflect(self, eventlog, meta_extra, staleness_threshold, auto_close_threshold):
        slot_id = (meta_extra or {}).get("slot_id")
        raw_events = eventlog.read_all()
        current_tick_id: Optional[int] = None
        if slot_id:
            for event in reversed(raw_events):
                if (
                    event.get("kind") == "autonomy_tick"
                    and event.get("meta", {}).get("slot_id") == slot_id
                ):
                    current_tick_id = event.get("id")
                    break

        events = raw_events
        if current_tick_id is not None:
            events = [e for e in raw_events if e.get("id", 0) < current_tick_id]
        events = [e for e in events if e.get("kind") != "autonomy_stimulus"]
        open_commitments = [
            e
            for e in events
            if e["kind"] == "commitment_open"
            and not any(
                c["kind"] == "commitment_close"
                and c.get("meta", {}).get("cid") == e.get("meta", {}).get("cid")
                for c in events
                if c["id"] > e["id"]
            )
        ]
        oldest = min((c for c in open_commitments), key=lambda c: c["id"], default=None)
        events_since = 0
        if oldest and staleness_threshold is not None:
            events_since = len([e for e in events if e["id"] > oldest["id"]])
        stale_flag = (
            1
            if staleness_threshold is not None and events_since > staleness_threshold
            else 0
        )
        # Auto-close stale commitments
        if (
            auto_close_threshold is not None
            and events_since > auto_close_threshold
            and open_commitments
        ):
            for c in open_commitments:
                eventlog.append(
                    kind="commitment_close",
                    content=f"CLOSE: {c['meta']['cid']}",
                    meta={"reason": "auto_close_stale", "cid": c["meta"]["cid"]},
                )
            open_commitments = []
            events_since = 0
        stale_flag = (
            1
            if staleness_threshold is not None and events_since > staleness_threshold
            else 0
        )
        content = (
            "{"
            f"commitments_reviewed:{len(open_commitments)}"
            f",stale:{stale_flag}"
            f",relevance:'all_active'"
            f",action:'maintain'"
            f",next:'monitor'"
            "}"
        )
        if len(open_commitments) > 0:
            content += "\nREF: ../other_pmm_v2.db#47"
        meta = {
            "synth": "v2",
            "source": meta_extra.get("source") if meta_extra else "unknown",
        }
        meta.update(meta_extra or {})
        return eventlog.append(kind="reflection", content=content, meta=meta)

    def decide_next_action(self) -> KernelDecision:
        events = self.eventlog.read_all()
        if not events:
            return KernelDecision("idle", "no events recorded", [])

        last_metrics = _last_event(events, "metrics_turn")
        if not last_metrics:
            return KernelDecision("idle", "no metrics_turn recorded yet", [])

        last_event_id = events[-1]["id"]

        last_autonomy_reflection = _last_event_matching(
            events,
            "reflection",
            lambda e: e.get("meta", {}).get("source") == "autonomy_kernel",
        )
        if last_autonomy_reflection is None:
            return KernelDecision(
                decision="reflect",
                reasoning="no autonomous reflection recorded yet",
                evidence=[last_event_id],
            )

        events_since_autonomy = _events_after(events, last_autonomy_reflection)

        if len(events_since_autonomy) >= self.thresholds["reflection_interval"]:
            return KernelDecision(
                decision="reflect",
                reasoning=f"reflection_interval reached ({len(events_since_autonomy)})",
                evidence=[last_event_id],
            )

        last_summary = _last_event(events, "summary_update")
        events_since_summary = _events_after(events, last_summary)
        autonomy_reflections_since_summary = [
            event
            for event in events_since_summary
            if event.get("kind") == "reflection"
            and event.get("meta", {}).get("source") == "autonomy_kernel"
        ]

        if (
            autonomy_reflections_since_summary
            and len(events_since_summary) >= self.thresholds["summary_interval"]
        ):
            return KernelDecision(
                decision="summarize",
                reasoning=f"summary_interval reached ({len(events_since_summary)})",
                evidence=[last_event_id],
            )

        return KernelDecision("idle", "no autonomous action needed", [])
