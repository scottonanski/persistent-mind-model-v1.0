# pmm/runtime/evolution_reporter.py

import hashlib
import json
from typing import Any

from pmm.constants import EventKinds
from pmm.storage.eventlog import EventLog


class EvolutionReporter:
    """Generate deterministic evolution summaries and emit auditable reports."""

    def __init__(self, log: EventLog):
        self.log = log

    def generate_summary(self, window: int = 100) -> dict[str, Any]:
        """Produce structured summary from last N events."""
        events: list[dict[str, Any]] = self.log.read_tail(limit=window)
        summary: dict[str, Any] = {"reflections": {}, "traits": {}, "commitments": {}}

        for e in events:
            kind = e.get("kind")

            if kind == EventKinds.REFLECTION:
                tag = e.get("meta", {}).get("tag")
                if tag:
                    summary["reflections"][tag] = summary["reflections"].get(tag, 0) + 1

            elif kind == EventKinds.TRAIT_UPDATE:
                trait = e.get("meta", {}).get("trait")
                delta = e.get("meta", {}).get("delta", 0.0)
                if trait:
                    summary["traits"][trait] = summary["traits"].get(trait, 0.0) + delta

            elif kind in [EventKinds.COMMITMENT_OPEN, EventKinds.COMMITMENT_CLOSE]:
                state = e.get("meta", {}).get("state")
                if state:
                    summary["commitments"][state] = (
                        summary["commitments"].get(state, 0) + 1
                    )

        return summary

    def _digest_summary(self, summary: dict[str, Any]) -> str:
        """Deterministic digest from summary payload."""
        payload = json.dumps(summary, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def emit_evolution_report(self, summary: dict[str, Any]) -> int | None:
        """Emit EVOLUTION event if summary non-empty, idempotent by digest."""
        if not any(summary.values()):
            return None

        digest = self._digest_summary(summary)

        # Check for existing reports with same digest
        existing_events = [
            e
            for e in self.log.read_all()
            if e.get("kind") == EventKinds.EVOLUTION
            and e.get("meta", {}).get("digest") == digest
        ]

        if existing_events:
            return existing_events[0]["id"]

        return self.log.append(
            kind=EventKinds.EVOLUTION,
            content="",  # no semantic meaning here
            meta={"digest": digest, "changes": summary},
        )
