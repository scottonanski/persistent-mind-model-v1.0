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


# --- Lightweight GAS nudge based on reflection content (ontology-locked) ---
PMM_POS = ("ledger", "traits", "commitment", "policy", "scene", "projection", "rebind")
ASSIST_NEG = ("how can i assist", "journal", "learn more")


def adjust_gas_from_text(
    eventlog, text: str, base_delta: float = 0.0, reason: str = "content_nudge"
) -> float:
    """Nudge GAS based on reflection content; clamp to [0,1]. Appends a metrics event.

    Reads last metrics event for GAS/IAS defaults; if none, uses 0.0/0.0.
    """
    t = (text or "").lower()
    pos = any(k in t for k in PMM_POS)
    neg = any(k in t for k in ASSIST_NEG)

    delta = float(base_delta)
    if pos:
        delta += 0.01
    if neg:
        delta -= 0.01

    import json

    try:
        row = eventlog._conn.execute(
            "SELECT meta FROM events WHERE kind='metrics' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except Exception:
        row = None
    gas_prev = 0.0
    ias_prev = 0.0
    if row:
        try:
            m = json.loads(row[0] or "{}")
            gas_prev = float(m.get("GAS", 0.0))
            ias_prev = float(m.get("IAS", 0.0))
        except Exception:
            gas_prev, ias_prev = 0.0, 0.0
    new_gas = max(0.0, min(1.0, gas_prev + delta))
    try:
        eventlog.append(
            "metrics",
            "",
            {"GAS": new_gas, "IAS": ias_prev, "gas_delta": delta, "reason": reason},
        )
    except Exception:
        pass
    return new_gas
