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

    def note_user_turn(self) -> None:
        self.turns_since += 1

    def reset(self) -> None:
        self.last_ts = time.time()
        self.turns_since = 0

    def should_reflect(
        self, now: float | None = None, novelty: float = 1.0
    ) -> Tuple[bool, str]:
        now = now or time.time()
        if self.turns_since < self.min_turns:
            return (False, "min_turns")
        if (now - self.last_ts) < self.min_seconds:
            return (False, "min_time")
        if novelty < 0.2:
            return (False, "low_novelty")
        return (True, "ok")
