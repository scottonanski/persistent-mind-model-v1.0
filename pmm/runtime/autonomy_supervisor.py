# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/autonomy_supervisor.py
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime

from pmm.core.event_log import EventLog


class AutonomySupervisor:
    """Deterministic slot-based supervisor for autonomy stimuli."""

    def __init__(self, eventlog: EventLog, epoch: str, interval_s: int) -> None:
        self.eventlog = eventlog
        self.epoch = epoch
        self.interval_s = interval_s
        self._running = False
        # In-memory cache of slot_ids that already have autonomy_stimulus events
        self.seen_slot_ids: set[str] = set()
        for ev in self.eventlog.read_all():
            if ev.get("kind") != "autonomy_stimulus":
                continue
            meta = ev.get("meta") or {}
            sid = meta.get("slot_id")
            if isinstance(sid, str) and sid:
                self.seen_slot_ids.add(sid)

    def _epoch_timestamp(self) -> float:
        """Parse epoch RFC3339 to Unix timestamp."""
        dt = datetime.fromisoformat(self.epoch.replace("Z", "+00:00"))
        return dt.timestamp()

    def _current_slot(self) -> int:
        """Calculate current slot deterministically."""
        now = time.time()
        epoch_ts = self._epoch_timestamp()
        return int((now - epoch_ts) // self.interval_s)

    def _slot_id(self, slot: int) -> str:
        """Deterministic slot ID."""
        payload = f"{self.epoch}{self.interval_s}{slot}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _stimulus_exists(self, slot_id: str) -> bool:
        """Check if autonomy_stimulus for this slot_id already exists."""
        return slot_id in self.seen_slot_ids

    def emit_stimulus_if_needed(self) -> None:
        """Emit autonomy_stimulus for current slot if not already present."""
        slot = self._current_slot()
        slot_id = self._slot_id(slot)
        if not self._stimulus_exists(slot_id):
            content = json.dumps({"slot": slot, "slot_id": slot_id}, sort_keys=True)
            self.eventlog.append(
                kind="autonomy_stimulus",
                content=content,
                meta={"source": "autonomy_supervisor", "slot_id": slot_id},
            )
            self.seen_slot_ids.add(slot_id)

    async def run_forever(self) -> None:
        """Run the supervisor loop indefinitely."""
        self._running = True
        while self._running:
            self.emit_stimulus_if_needed()
            await asyncio.sleep(self.interval_s)

    def stop(self) -> None:
        """Stop the supervisor loop."""
        self._running = False
