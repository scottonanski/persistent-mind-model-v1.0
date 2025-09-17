from __future__ import annotations
from typing import Iterable, Tuple


def compute_ias_gas(events: Iterable[dict]) -> Tuple[float, float]:
    """Compute simple IAS/GAS proxies from a sliding window of events.

    IAS: commitment close rate over opens in the last 50 events (default 0.5 if no opens).
         Boosted if identity adoption follows valid semantic cues (confidence >= 0.8).
    GAS: normalized activity (opens + reflections) over last 50 events, clamped to [0,1].
         Incremented if new identity leads to novel commitments or reflections within N turns.
    """
    evs = list(events)[-50:]
    opens = sum(1 for e in evs if e.get("kind") == "commitment_open")
    closes = sum(1 for e in evs if e.get("kind") == "commitment_close")
    ias = (closes / opens) if opens else 0.5

    refl = sum(1 for e in evs if e.get("kind") == "reflection")
    gas_raw = opens + refl
    gas = min(1.0, gas_raw / 10.0)

    # Check for recent identity adoption events that might affect metrics
    recent_identity_adopts = [e for e in evs if e.get("kind") == "identity_adopt"]

    # IAS boost if adoption follows valid semantic cues (high confidence)
    for adopt_event in recent_identity_adopts:
        meta = adopt_event.get("meta", {})
        confidence = meta.get("confidence", 0.0)
        # Boost IAS if confidence is high (>= 0.8)
        if confidence >= 0.8:
            ias = min(1.0, ias + 0.1)

    # GAS increment if new identity leads to novel commitments or reflections
    # We'll check for commitment_open or reflection events that occurred after identity adoption
    for adopt_event in recent_identity_adopts:
        adopt_id = adopt_event.get("id", 0)
        # Look for novel commitments or reflections that came after this adoption
        novel_events = [
            e
            for e in evs
            if e.get("id", 0) > adopt_id
            and e.get("kind") in ["commitment_open", "reflection"]
        ]

        # If there are new events after adoption, increment GAS
        if novel_events:
            gas = min(1.0, gas + 0.1)

    # Clamp to [0,1]
    ias = max(0.0, min(1.0, ias))
    gas = max(0.0, min(1.0, gas))
    return ias, gas
