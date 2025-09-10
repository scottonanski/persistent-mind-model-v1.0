from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Tuple


@dataclass
class ReflectionCooldown:
    min_turns: int = 2
    min_seconds: float = 60.0
    last_ts: float = 0.0
    turns_since: int = 0
    novelty_threshold: float = 0.2

    def note_user_turn(self) -> None:
        self.turns_since += 1

    def reset(self) -> None:
        self.last_ts = time.time()
        self.turns_since = 0

    def should_reflect(
        self,
        now: float | None = None,
        novelty: float = 1.0,
        *,
        override_min_turns: int | None = None,
        override_min_seconds: int | None = None,
    ) -> Tuple[bool, str]:
        now = now or time.time()
        # Use one-shot overrides for this call only (no persisted changes)
        min_turns = (
            int(override_min_turns)
            if override_min_turns is not None
            else self.min_turns
        )
        min_seconds = (
            float(override_min_seconds)
            if override_min_seconds is not None
            else self.min_seconds
        )
        if self.turns_since < min_turns:
            return (False, "min_turns")
        if (now - self.last_ts) < min_seconds:
            return (False, "min_time")
        if novelty < float(self.novelty_threshold):
            return (False, "low_novelty")
        return (True, "ok")
