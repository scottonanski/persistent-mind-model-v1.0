"""Proactive commitment tracking and reinforcement for PMM.

Provides deterministic assessment of commitment health and proactive
adjustment suggestions. All computations are pure and side-effect free.
"""

from __future__ import annotations
from typing import Dict, List, Optional
import hashlib
import json


class ProactiveCommitmentManager:
    """
    Deterministic assessment of commitments and proactive reinforcement.
    """

    def evaluate_commitment_health(self, events: List[dict]) -> Dict:
        """
        Input: list of commitment-related events (open/close/reopen, newest last).
        Output: dict with deterministic stats.

        Args:
            events: List of commitment-related event dictionaries

        Returns:
            Dictionary with commitment health statistics
        """
        if not events:
            return {
                "total_opened": 0,
                "total_closed": 0,
                "close_rate": 0.0,
                "avg_open_span": -1.0,
                "streak_open_failures": 0,
            }

        # Track commitment lifecycle
        total_opened = 0
        total_closed = 0
        open_spans = []  # List of spans between open and close
        consecutive_opens = 0  # Current streak of opens without close

        # Track open commitments and their positions
        open_positions = []  # List of (index, kind) for tracking spans

        # Process events to track opens and closes
        for i, event in enumerate(events):
            kind = event.get("kind", "")

            if kind == "commitment_open":
                total_opened += 1
                consecutive_opens += 1
                open_positions.append(i)

            elif kind == "commitment_close":
                total_closed += 1
                consecutive_opens = 0  # Reset streak on any close

                # Match with oldest open for span calculation
                if open_positions:
                    open_pos = open_positions.pop(0)  # FIFO matching
                    span = i - open_pos
                    open_spans.append(span)

            elif kind == "commitment_reopen":
                # Treat reopen as a new open
                total_opened += 1
                consecutive_opens += 1
                open_positions.append(i)

        # Calculate metrics
        close_rate = total_closed / max(1, total_opened)
        avg_open_span = sum(open_spans) / len(open_spans) if open_spans else -1.0
        streak_open_failures = len(open_positions)  # Remaining unmatched opens

        return {
            "total_opened": total_opened,
            "total_closed": total_closed,
            "close_rate": close_rate,
            "avg_open_span": avg_open_span,
            "streak_open_failures": streak_open_failures,
        }

    def suggest_commitment_adjustments(self, health: Dict) -> List[Dict]:
        """
        Pure function. Returns a list of adjustment suggestions.

        Args:
            health: Health dictionary from evaluate_commitment_health

        Returns:
            List of adjustment suggestion dictionaries
        """
        suggestions = []

        close_rate = health.get("close_rate", 0.0)
        avg_open_span = health.get("avg_open_span", -1.0)
        streak_open_failures = health.get("streak_open_failures", 0)

        # Deterministic mapping based on health metrics
        if close_rate < 0.5:
            suggestions.append({"action": "shorten_ttl", "reason": "low close rate"})

        if avg_open_span > 20:
            suggestions.append(
                {"action": "reinforce_reflection", "reason": "long spans"}
            )

        if streak_open_failures >= 3:
            suggestions.append(
                {"action": "cap_new_opens", "reason": "multiple failures"}
            )

        return suggestions

    def maybe_emit_health_report(self, eventlog, health: Dict) -> Optional[str]:
        """
        Append exactly one event per unique health digest.
        Idempotent by digest. Returns event id or None if skipped.

        Args:
            eventlog: EventLog instance to append to
            health: Health dictionary to report

        Returns:
            Event ID string or None if skipped
        """
        # Calculate stable digest
        digest = self._calculate_health_digest(health)

        # Check for idempotency
        if self._already_emitted_health(eventlog, digest):
            return None

        # Prepare metadata
        meta = {
            "component": "commitment_manager",
            "health": health,
            "deterministic": True,
            "digest": digest,
        }

        # Emit commitment_health event
        event_id = eventlog.append(
            kind="commitment_health", content="evaluation", meta=meta
        )

        return str(event_id)

    def _calculate_health_digest(self, health: Dict) -> str:
        """Calculate stable SHA256 digest over health dictionary."""
        # Sort keys for deterministic serialization
        health_json = json.dumps(health, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(health_json.encode("utf-8")).hexdigest()

    def _already_emitted_health(self, eventlog, digest: str) -> bool:
        """Check if health report with this digest has already been emitted."""
        # Query existing commitment_health events
        all_events = eventlog.read_all()
        for event in all_events:
            if (
                event.get("kind") == "commitment_health"
                and event.get("content") == "evaluation"
            ):

                event_meta = event.get("meta", {})
                if (
                    event_meta.get("component") == "commitment_manager"
                    and event_meta.get("digest") == digest
                ):
                    return True
        return False
