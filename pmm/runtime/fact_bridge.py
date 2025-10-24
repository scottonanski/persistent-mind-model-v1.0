"""Fact bridge for authoritative ledger queries.

Provides ground-truth assertions for volatile facts (stage, commitments, event count).
Used to prevent Echo from guessing or hallucinating ledger state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pmm.storage.eventlog import EventLog


class FactBridge:
    """Bridge to authoritative ledger facts."""

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog

    def assert_event_count(self) -> int:
        """Return exact event count from ledger."""
        return self.eventlog.get_max_id()

    def assert_open_commitments(self) -> int:
        """Return exact count of open commitments from ledger.

        Scans ledger for commitment_open events not matched by
        commitment_close or commitment_expire events.
        """
        try:
            events = self.eventlog.read_all()
        except Exception:
            return 0

        # Track open commitments
        open_cids: set[str] = set()
        for ev in events:
            kind = ev.get("kind")
            meta = ev.get("meta") or {}
            cid = meta.get("cid")

            if not cid:
                continue

            if kind == "commitment_open":
                open_cids.add(str(cid))
            elif kind in ("commitment_close", "commitment_expire"):
                open_cids.discard(str(cid))

        return len(open_cids)

    def assert_stage(self) -> str | None:
        """Return current stage from ledger.

        Scans for most recent stage_update event.
        """
        try:
            events = self.eventlog.read_tail(limit=1000)
        except Exception:
            return None

        # Find most recent stage_update
        for ev in reversed(events):
            if ev.get("kind") == "stage_update":
                meta = ev.get("meta") or {}
                stage_to = meta.get("to")
                if stage_to:
                    return str(stage_to)

        return None
