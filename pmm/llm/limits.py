from __future__ import annotations
import time
from dataclasses import dataclass
import os as _os

# ---- deterministic ceilings (per tick) ----
# Allow environment overrides for power users (keeps defaults unchanged).
try:
    MAX_CHAT_CALLS_PER_TICK: int = int(_os.environ.get("PMM_MAX_CHAT_PER_TICK", "4"))
except Exception:
    MAX_CHAT_CALLS_PER_TICK = 4
try:
    MAX_EMBED_CALLS_PER_TICK: int = int(_os.environ.get("PMM_MAX_EMBED_PER_TICK", "20"))
except Exception:
    MAX_EMBED_CALLS_PER_TICK = 20

# Sentinel used by higher-level wrappers when an operation is skipped due to budget
RATE_LIMITED = object()


@dataclass
class _Counts:
    chat: int = 0
    embed: int = 0


class TickBudget:
    """Deterministic budget keyed by tick_id."""

    def __init__(self):
        self._tick_id: int | None = None
        self._counts = _Counts()

    def start_tick(self, tick_id: int | None):
        if tick_id is None:
            # still deterministic: treat as a single global bucket
            return
        if tick_id != self._tick_id:
            self._tick_id = tick_id
            self._counts = _Counts()

    def allow_chat(self) -> bool:
        if self._counts.chat >= MAX_CHAT_CALLS_PER_TICK:
            return False
        self._counts.chat += 1
        return True

    def allow_embed(self) -> bool:
        if self._counts.embed >= MAX_EMBED_CALLS_PER_TICK:
            return False
        self._counts.embed += 1
        return True


def timed_call(fn):
    """Return (ok, ms, out_or_exc). ok=False if exception raised (we still log latency)."""
    t0 = time.monotonic()
    try:
        out = fn()
        dt_ms = (time.monotonic() - t0) * 1000.0
        return True, dt_ms, out
    except Exception as e:  # non-fatal: caller decides what to do
        dt_ms = (time.monotonic() - t0) * 1000.0
        return False, dt_ms, e
