"""Loop scheduler (Stage 3 extraction).

Provides a minimal, behavior-preserving thread scheduler that periodically
invokes a supplied `on_tick` callable. This isolates timing/cancellation from
the AutonomyLoop business logic.
"""

from __future__ import annotations

import threading as _threading
import time as _time
from collections.abc import Callable


class LoopScheduler:
    """Thread-based periodic scheduler for loop ticks.

    Behavior mirrors the legacy AutonomyLoop runner: fixed interval, no jitter
    by default, graceful stop via an event, and bounded join on stop.
    """

    def __init__(
        self,
        *,
        on_tick: Callable[[], None],
        interval_seconds: float = 60.0,
        name: str = "PMM-AutonomyLoop",
        jitter_fn: Callable[[], float] | None = None,
        backpressure_fn: Callable[[], bool] | None = None,
    ) -> None:
        self._on_tick = on_tick
        self._interval = max(0.01, float(interval_seconds))
        self._name = str(name)
        self._jitter_fn = jitter_fn
        self._backpressure_fn = backpressure_fn

        self._stop = _threading.Event()
        self._thread: _threading.Thread | None = None

    # --- lifecycle ---
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = _threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=self._interval * 2)
        self._thread = None

    def is_running(self) -> bool:
        t = self._thread
        return bool(t and t.is_alive())

    # --- configuration ---
    def update_interval(self, interval_seconds: float) -> None:
        self._interval = max(0.01, float(interval_seconds))

    # --- internals ---
    def _run(self) -> None:
        next_at = _time.time() + self._interval
        while not self._stop.is_set():
            now = _time.time()
            if now >= next_at:
                try:
                    # Optional backpressure: if True, skip this tick
                    if self._backpressure_fn and self._backpressure_fn():
                        pass
                    else:
                        self._on_tick()
                except Exception:
                    # Keep heartbeat resilient
                    pass
                # Compute next interval with optional jitter (non-negative)
                jitter = 0.0
                if self._jitter_fn:
                    try:
                        jitter = float(self._jitter_fn())
                    except Exception:
                        jitter = 0.0
                if jitter < 0.0:
                    jitter = 0.0
                next_at = now + self._interval + jitter
            # Small wait to avoid busy spin and allow prompt shutdown
            self._stop.wait(0.05)


__all__ = ["LoopScheduler"]
