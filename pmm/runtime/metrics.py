from __future__ import annotations
from typing import Iterable, Tuple


def compute_ias_gas(events: Iterable[dict]) -> Tuple[float, float]:
    """Compute simple IAS/GAS proxies from a sliding window of events.

    IAS: commitment close rate over opens in the last 50 events (default 0.5 if no opens).
    GAS: normalized activity (opens + reflections) over last 50 events, clamped to [0,1].
    """
    evs = list(events)[-50:]
    opens = sum(1 for e in evs if e.get("kind") == "commitment_open")
    closes = sum(1 for e in evs if e.get("kind") == "commitment_close")
    ias = (closes / opens) if opens else 0.5

    refl = sum(1 for e in evs if e.get("kind") == "reflection")
    gas_raw = opens + refl
    gas = min(1.0, gas_raw / 10.0)

    # Clamp to [0,1]
    ias = max(0.0, min(1.0, ias))
    gas = max(0.0, min(1.0, gas))
    return ias, gas
