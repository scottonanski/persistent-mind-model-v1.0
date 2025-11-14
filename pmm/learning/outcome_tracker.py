# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/learning/outcome_tracker.py
"""Outcome observation tracking for adaptive learning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from pmm.core.event_log import EventLog


@dataclass(frozen=True)
class OutcomeObservation:
    event_id: int
    commitment_id: str
    action_kind: str
    action_payload: str
    observed_result: str  # "success", "failure", "partial"
    evidence_event_ids: tuple[int, ...]


def extract_outcome_observations(log: EventLog) -> List[OutcomeObservation]:
    """Extract outcome observations from event log."""
    observations = []
    for event in log.read_all():
        if event.get("kind") == "outcome_observation":
            try:
                data = json.loads(event.get("content") or "{}")
                if isinstance(data, dict):
                    observations.append(
                        OutcomeObservation(
                            event_id=event["id"],
                            commitment_id=data.get("commitment_id", ""),
                            action_kind=data.get("action_kind", ""),
                            action_payload=data.get("action_payload", ""),
                            observed_result=data.get("observed_result", ""),
                            evidence_event_ids=tuple(
                                data.get("evidence_event_ids", [])
                            ),
                        )
                    )
            except (ValueError, TypeError):
                continue  # Skip malformed
    return observations


def build_outcome_observation_content(
    commitment_id: str,
    action_kind: str,
    action_payload: str,
    observed_result: str,
    evidence_event_ids: Sequence[int],
) -> Dict[str, Any]:
    """Build content dict for outcome_observation event."""
    return {
        "commitment_id": commitment_id,
        "action_kind": action_kind,
        "action_payload": action_payload,
        "observed_result": observed_result,
        "evidence_event_ids": list(evidence_event_ids),
    }
