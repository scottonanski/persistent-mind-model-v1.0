from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Tuple, List, Dict


@dataclass
class ReflectionCooldown:
    min_turns: int = 2
    min_seconds: float = 60.0
    last_ts: float = 0.0
    turns_since: int = 0
    novelty_threshold: float = 0.2
    last_effective_novelty_threshold: float = 0.0

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
        events: List[Dict] | None = None,
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
        # If recent events are provided, consume latest policy_update for cooldown
        # without mutating internal state; fallback to current threshold.
        novelty_thr = float(self.novelty_threshold)
        if events:
            try:
                for ev in reversed(events):
                    if ev.get("kind") != "policy_update":
                        continue
                    m = ev.get("meta") or {}
                    if str(m.get("component")) != "cooldown":
                        continue
                    params = m.get("params") or {}
                    if "novelty_threshold" in params:
                        novelty_thr = float(params.get("novelty_threshold"))
                        break
            except Exception:
                # Never fail gating due to policy parsing issues
                pass
        # Clamp to avoid runaway policy values starving reflections.
        try:
            novelty_thr = min(0.8, max(0.0, float(novelty_thr)))
        except Exception:
            novelty_thr = 0.8
        self.last_effective_novelty_threshold = float(novelty_thr)

        # High-novelty bypass: if novelty is very high (≥0.95), allow reflection
        # even if turn/time gates haven't been met yet. This enables deep
        # philosophical conversations to trigger reflections naturally.
        high_novelty_bypass = novelty >= 0.95

        if self.turns_since < min_turns and not high_novelty_bypass:
            return (False, "min_turns")
        if (now - self.last_ts) < min_seconds and not high_novelty_bypass:
            return (False, "min_time")
        if novelty < novelty_thr:
            return (False, "due_to_low_novelty")
        return (True, "ok")
