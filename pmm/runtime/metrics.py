from __future__ import annotations
from typing import Iterable, Tuple, List, Dict, Optional

# Deterministic score movement parameters (ledger-anchored, dev-tuned)

# Identity stability
_STABLE_IDENTITY_WINDOW_TICKS: int = 1    # reward every tick of stability (not 3)
_IAS_PER_STABLE_WINDOW: float = 0.05      # +0.05 IAS per stable tick (~every 10s)
_IAS_FLIP_FLOP_PENALTY: float = 0.10      # clear hit for quick flip-flops

# Commitments
_GAS_PER_COMMIT_OPEN_NOVEL: float = 0.05  # small bump for opening something new
_GAS_PER_COMMIT_CLOSE_CLEAN: float = 0.10 # bigger bump when you actually close
_GAS_FORCED_CLOSE_PENALTY: float = 0.05   # closing by force hurts

# Reflections
_GAS_REFLECTION_REPEAT_PENALTY: float = 0.02 # repeating same reflection drags growth
_IAS_REFLECTION_IDENTITY_BONUS: float = 0.02 # identity-linked reflection nudges IAS

# Decay
_DECAY_PER_TICK: float = 0.999            # very slow natural decay (keeps pressure on)

# Novelty/repeat windows
_OPEN_NOVEL_WINDOW: int = 20
_REPEAT_REFLECT_WINDOW: int = 8



def _clip(v: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(float(v), hi))
    except Exception:
        return lo


def _norm_text(s: Optional[str]) -> str:
    try:
        return (s or "").strip().lower()
    except Exception:
        return ""


def compute_ias_gas(events: Iterable[dict]) -> Tuple[float, float]:
    """Compute IAS (identity stability) and GAS (growth via commitments) from the ledger.

    Deterministic, event-driven rules:
    - Identity stability: +0.01 per stable window of N autonomy ticks without re-adoption.
      Flip-flop penalty: -0.02 if a re-adopt occurs within N ticks of the last adoption.
    - Commitments: +0.01 GAS for novel commitment_open (not a duplicate in recent window);
      +0.05 GAS for commitment_close; -0.02 for commitment_expire/forced.
    - Reflections: small IAS bonus if identity-linked; -0.01 GAS if repeated reflection content.
    - Decay: multiply IAS and GAS by 0.999 per autonomy_tick; floors at IAS>=0.5, GAS>=0.0.

    Clip outputs to [0.0, 1.0] and apply IAS floor of 0.5.
    """
    evs: List[Dict] = list(events)  # deterministic order
    # Baselines
    ias: float = 0.5
    gas: float = 0.0

    # Map event id -> tick index and collect tick ids for window math
    tick_ids: List[int] = []
    tick_index_by_eid: Dict[int, int] = {}
    tick = 0
    for ev in evs:
        try:
            eid = int(ev.get("id") or 0)
        except Exception:
            eid = 0
        if ev.get("kind") == "autonomy_tick":
            tick += 1
            tick_ids.append(eid)
        tick_index_by_eid[eid] = tick

    # Trait multipliers (soft influence) — derived deterministically from projection if present
    try:
        from pmm.storage.projection import build_self_model as _build_self_model

        model = _build_self_model(evs)
        traits = (model or {}).get("traits") or {}
        openness = float(traits.get("openness", 0.5))
        conscientiousness = float(traits.get("conscientiousness", 0.5))
    except Exception:
        openness = 0.5
        conscientiousness = 0.5

    cons_mult = 1.0 + (conscientiousness - 0.5) * 0.5  # [0.75, 1.25]
    open_mult = 1.0 + (openness - 0.5) * 0.3  # [0.85, 1.15]

    # Novelty and repetition trackers
    recent_opens: List[str] = []
    recent_reflections: List[str] = []

    # Identity adoption tracking for stability windows
    adopt_events: List[Tuple[int, str]] = []  # (tick_index, name)
    last_adopt_tick: Optional[int] = None
    last_adopt_name: Optional[str] = None

    # First pass: incremental adjustments per event and collect adoptions
    for ev in evs:
        kind = ev.get("kind")
        try:
            eid = int(ev.get("id") or 0)
        except Exception:
            eid = 0
        tix = int(tick_index_by_eid.get(eid, 0))
        if kind == "identity_adopt":
            # Name from meta.sanitized, meta.name, or content
            m = ev.get("meta") or {}
            nm = str(m.get("sanitized") or m.get("name") or ev.get("content") or "").strip()
            adopt_events.append((tix, nm))
            # Flip-flop penalty if within the stable window
            if last_adopt_tick is not None and last_adopt_name and nm:
                if (tix - int(last_adopt_tick)) <= _STABLE_IDENTITY_WINDOW_TICKS and (
                    _norm_text(nm) != _norm_text(last_adopt_name)
                ):
                    ias -= _IAS_FLIP_FLOP_PENALTY
            last_adopt_tick = tix
            last_adopt_name = nm
        elif kind == "commitment_open":
            txt = _norm_text(ev.get("content"))
            is_novel = txt and (txt not in recent_opens)
            if is_novel:
                gas += _GAS_PER_COMMIT_OPEN_NOVEL * open_mult
                # Maintain novelty window
                recent_opens.append(txt)
                if len(recent_opens) > _OPEN_NOVEL_WINDOW:
                    recent_opens.pop(0)
        elif kind == "commitment_close":
            gas += _GAS_PER_COMMIT_CLOSE_CLEAN * cons_mult
        elif kind == "commitment_expire":
            gas -= _GAS_FORCED_CLOSE_PENALTY
        elif kind == "reflection":
            txt = _norm_text(ev.get("content"))
            # Identity-linked bonus
            if txt and ("identity" in txt or "name" in txt):
                ias += _IAS_REFLECTION_IDENTITY_BONUS
            # Repetition penalty (looping reflections)
            if txt:
                rep = sum(1 for t in recent_reflections if t == txt)
                if rep >= 1:  # repeated within window
                    gas -= _GAS_REFLECTION_REPEAT_PENALTY
                recent_reflections.append(txt)
                if len(recent_reflections) > _REPEAT_REFLECT_WINDOW:
                    recent_reflections.pop(0)
        elif kind == "invariant_violation":
            ias -= 0.05
            gas -= 0.05
        elif kind == "autonomy_tick":
            ias *= _DECAY_PER_TICK
            gas *= _DECAY_PER_TICK

    # Second pass: apply stability rewards for each adoption over completed windows
    if adopt_events:
        # Ensure sorted by tick index
        adopt_events.sort(key=lambda t: t[0])
        # Determine end tick (up to last observed)
        end_tick = tick if tick > 0 else (tick_ids and len(tick_ids)) or 0
        for i, (tix, _nm) in enumerate(adopt_events):
            next_tix = adopt_events[i + 1][0] if (i + 1) < len(adopt_events) else end_tick
            dt = max(0, int(next_tix) - int(tix))
            if _STABLE_IDENTITY_WINDOW_TICKS > 0:
                windows = dt // _STABLE_IDENTITY_WINDOW_TICKS
                if windows > 0:
                    ias += float(windows) * _IAS_PER_STABLE_WINDOW

    # Clip and floor
    ias = _clip(ias, 0.5, 1.0)
    gas = _clip(gas, 0.0, 1.0)
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
