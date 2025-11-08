# Path: pmm/runtime/executors.py
"""Runtime executors activated via exec_bind configurations."""

from __future__ import annotations

import json
from typing import Dict

from pmm.core.event_log import EventLog
from pmm.core.commitment_manager import CommitmentManager


class IdleMonitorExecutor:
    """Emit metric checks and escalate when idle thresholds are exceeded."""

    def __init__(self, eventlog: EventLog, cid: str, params: Dict[str, object]) -> None:
        self.eventlog = eventlog
        self.cid = cid
        self.threshold = int(params.get("threshold", 3))
        self.idle_count = 0
        self.commitments = CommitmentManager(eventlog)

    def tick(self) -> None:
        self.idle_count += 1
        metric_payload = {
            "cid": self.cid,
            "idle_count": self.idle_count,
        }
        self.eventlog.append(
            kind="metric_check",
            content=json.dumps(metric_payload, sort_keys=True, separators=(",", ":")),
            meta={"source": "idle_monitor"},
        )

        if self.idle_count > self.threshold:
            kernel_payload = {
                "trigger": "idle_threshold_exceeded",
                "cid": self.cid,
            }
            self.eventlog.append(
                kind="autonomy_kernel",
                content=json.dumps(
                    kernel_payload, sort_keys=True, separators=(",", ":")
                ),
                meta={"source": "idle_monitor"},
            )
            goal_payload = {
                "goal": "explore_rsm_drift",
                "cid": self.cid,
            }
            self.eventlog.append(
                kind="internal_goal_created",
                content=json.dumps(goal_payload, sort_keys=True, separators=(",", ":")),
                meta={"source": "idle_monitor"},
            )
            self.commitments.open_internal(
                goal="explore_rsm_drift",
                reason="idle_threshold_exceeded",
            )
            self.idle_count = 0
