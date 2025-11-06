from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import json

from pmm_v2.core.event_log import EventLog
from pmm_v2.core.ledger_mirror import LedgerMirror
from pmm_v2.core.commitment_manager import CommitmentManager


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

    INTERNAL_GOAL_MONITOR_RSM = "monitor_rsm_evolution"
    INTERNAL_GOAL_ANALYZE_GAPS = "analyze_knowledge_gaps"
    KNOWLEDGE_GAP_THRESHOLD = 3
    RSM_EVENT_INTERVAL = 50
    SIGNIFICANT_TENDENCY_THRESHOLD = 5

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
        self._goal_state: Dict[str, Dict[str, int]] = {}
        self._commitments = CommitmentManager(eventlog)
        self.last_gap_analysis_cid: Optional[str] = None

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
        content_dict: Dict[str, object] = {
            "commitments_reviewed": len(open_commitments),
            "stale": stale_flag,
            "relevance": "all_active",
            "action": "maintain",
            "next": "monitor",
        }
        if len(open_commitments) > 0:
            content_dict["refs"] = ["../other_pmm_v2.db#47"]
        internal_open = CommitmentManager(eventlog).get_open_commitments(
            origin="autonomy_kernel"
        )
        content_dict["internal_goals"] = [
            (ev.get("meta") or {}).get("cid")
            for ev in internal_open
            if (ev.get("meta") or {}).get("cid")
        ]
        meta = {
            "synth": "v2",
            "source": meta_extra.get("source") if meta_extra else "unknown",
        }
        meta.update(meta_extra or {})
        return eventlog.append(
            kind="reflection",
            content=json.dumps(content_dict, sort_keys=True, separators=(",", ":")),
            meta=meta,
        )

    def decide_next_action(self) -> KernelDecision:
        self.execute_internal_goal(self.INTERNAL_GOAL_MONITOR_RSM)
        mirror = LedgerMirror(self.eventlog, listen=False)
        gaps = mirror.rsm_knowledge_gaps()
        gap_commitments = self._open_gap_commitments()
        if not gap_commitments and gaps > self.KNOWLEDGE_GAP_THRESHOLD:
            reason = f"gaps={gaps}"
            cid = self._commitments.open_internal(
                self.INTERNAL_GOAL_ANALYZE_GAPS, reason=reason
            )
            if cid:
                self.last_gap_analysis_cid = cid
                gap_commitments = self._open_gap_commitments()
        elif gap_commitments:
            latest_meta = gap_commitments[-1].get("meta") or {}
            self.last_gap_analysis_cid = latest_meta.get("cid")
        else:
            self.last_gap_analysis_cid = None
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

    def _open_gap_commitments(self) -> List[Dict[str, Any]]:
        return [
            event
            for event in self._commitments.get_open_commitments(
                origin="autonomy_kernel"
            )
            if (event.get("meta") or {}).get("goal") == self.INTERNAL_GOAL_ANALYZE_GAPS
        ]

    def execute_internal_goal(self, goal: str) -> Optional[int]:
        if goal != self.INTERNAL_GOAL_MONITOR_RSM:
            return None

        events = self.eventlog.read_all()
        if not events:
            return None

        open_goal = self._find_open_internal_goal(goal, events)
        if not open_goal:
            return None

        current_event_id = events[-1]["id"]
        state = self._goal_state.setdefault(
            goal,
            {"last_check_id": self._initial_goal_anchor(goal, open_goal, events)},
        )
        last_check_id = state["last_check_id"]

        if current_event_id <= last_check_id:
            return None

        if current_event_id - last_check_id < self.RSM_EVENT_INTERVAL:
            return None

        mirror = LedgerMirror(self.eventlog, listen=False)
        diff = mirror.diff_rsm(last_check_id, current_event_id)

        if not self._is_significant_rsm_change(diff):
            self._goal_state.pop(goal, None)
            self._close_internal_goal(open_goal, goal)
            return None

        reflection_id = self._append_rsm_reflection(
            diff, last_check_id, current_event_id
        )
        self._goal_state[goal]["last_check_id"] = reflection_id
        return reflection_id

    def _is_significant_rsm_change(self, diff: Dict[str, object]) -> bool:
        tendencies = diff.get("tendencies_delta", {}) or {}
        if any(
            abs(int(value)) > self.SIGNIFICANT_TENDENCY_THRESHOLD
            for value in tendencies.values()
        ):
            return True
        if diff.get("gaps_added") or diff.get("gaps_resolved"):
            return True
        return False

    def _find_open_internal_goal(
        self, goal: str, events: List[Dict[str, object]]
    ) -> Optional[Dict[str, object]]:
        open_event: Optional[Dict[str, object]] = None
        for event in events:
            if (
                event.get("kind") == "commitment_open"
                and event.get("meta", {}).get("goal") == goal
            ):
                open_event = event
            elif (
                open_event
                and event.get("kind") == "commitment_close"
                and event.get("meta", {}).get("cid")
                == open_event.get("meta", {}).get("cid")
            ):
                open_event = None
        return open_event

    def _initial_goal_anchor(
        self,
        goal: str,
        open_goal: Dict[str, object],
        events: List[Dict[str, object]],
    ) -> int:
        if goal == self.INTERNAL_GOAL_MONITOR_RSM:
            summary_id = self._last_summary_event_id(events)
            if summary_id is not None:
                return summary_id
            return int(open_goal.get("id", 0))
        return 0

    def _last_summary_event_id(self, events: List[Dict[str, object]]) -> Optional[int]:
        for event in reversed(events):
            if event.get("kind") == "summary_update":
                return int(event["id"])
        return None

    def _append_rsm_reflection(
        self, diff: Dict[str, object], start_id: int, end_id: int
    ) -> int:
        tendencies = diff.get("tendencies_delta", {}) or {}
        ordered_tendencies = {
            key: int(tendencies[key]) for key in sorted(tendencies.keys())
        }
        payload = {
            "action": self.INTERNAL_GOAL_MONITOR_RSM,
            "tendencies_delta": ordered_tendencies,
            "gaps_added": diff.get("gaps_added", []),
            "gaps_resolved": diff.get("gaps_resolved", []),
            "from_event": int(start_id),
            "to_event": int(end_id),
            "next": "monitor",
        }
        meta = {
            "source": "autonomy_kernel",
            "goal": self.INTERNAL_GOAL_MONITOR_RSM,
        }
        return self.eventlog.append(
            kind="reflection",
            content=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            meta=meta,
        )

    def _close_internal_goal(
        self, open_goal: Dict[str, object], goal: str
    ) -> Optional[int]:
        cid = (open_goal.get("meta") or {}).get("cid")
        if not cid:
            return None
        return self.eventlog.append(
            kind="commitment_close",
            content=f"Commitment closed: {cid}",
            meta={
                "source": "autonomy_kernel",
                "cid": cid,
                "goal": goal,
                "reason": "rsm_stable",
            },
        )
