from __future__ import annotations
from typing import Iterable, Tuple, List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)

# Deterministic score movement parameters (ledger-anchored, dev-tuned)

# Identity stability - responsive to user interactions (3s ticks, 5-tick windows = 15s bonuses)
_STABLE_IDENTITY_WINDOW_TICKS: int = 5  # reward every 5 ticks of stability (15 seconds)
_IAS_PER_STABLE_WINDOW: float = (
    0.03  # +0.03 IAS per stable window (more impactful growth)
)
_IAS_FLIP_FLOP_PENALTY: float = 0.08  # gentler penalty for quick flip-flops

# Commitments - more responsive for dynamic evolution
_GAS_PER_COMMIT_OPEN_NOVEL: float = 0.07  # increased from 0.05 for faster GAS growth
_GAS_PER_COMMIT_CLOSE_CLEAN: float = (
    0.12  # increased from 0.10 for more impactful closes
)
_GAS_FORCED_CLOSE_PENALTY: float = 0.0  # disabled - let clean closes dominate

# Reflections - conservative to avoid noise
_GAS_REFLECTION_REPEAT_PENALTY: float = 0.0  # disabled - too noisy in practice
_IAS_REFLECTION_IDENTITY_BONUS: float = 0.01  # small identity-linked reflection bonus

# Decay - very gentle to preserve signal
_DECAY_PER_TICK: float = 0.9995  # slower decay for longer-lived systems

# Novelty/repeat windows - tick-based for proper timing
_OPEN_NOVEL_WINDOW_TICKS: int = 20  # ticks since last same-open to count as novel
_REPEAT_REFLECT_WINDOW_TICKS: int = 8  # ticks since last same-reflection


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


def get_ias_gas_from_db(eventlog) -> Tuple[float, float, int]:
    """Read latest IAS/GAS from database metrics event.

    Returns:
        Tuple of (ias, gas, last_metrics_event_id)
        If no metrics event found, returns (0.0, 0.0, 0)
    """
    try:
        from pmm.constants import EventKinds

        with eventlog._lock:
            row = eventlog._conn.execute(
                "SELECT id, meta FROM events WHERE kind=? ORDER BY id DESC LIMIT 1",
                (EventKinds.METRICS_UPDATE,),
            ).fetchone()
        if row:
            event_id, meta_str = row
            meta = json.loads(meta_str or "{}")
            ias = float(meta.get("IAS", 0.0))
            gas = float(meta.get("GAS", 0.0))
            return ias, gas, int(event_id)
        return 0.0, 0.0, 0  # No metrics event found
    except Exception as e:
        logger.error(f"Error reading metrics from DB: {e}")
        return 0.0, 0.0, 0


def needs_metrics_recomputation(eventlog, last_metrics_id: int) -> bool:
    """Check if metrics need recomputation due to newer relevant events."""
    if last_metrics_id == 0:
        return True  # No metrics event found

    try:
        # Check for events after last metrics that affect IAS/GAS
        relevant_kinds = [
            "commitment_open",
            "commitment_close",
            "commitment_expire",
            "identity_adopt",
            "reflection",
            "invariant_violation",
            "autonomy_tick",
        ]
        placeholders = ",".join(["?" for _ in relevant_kinds])
        query = f"""
            SELECT COUNT(*) FROM events
            WHERE id > ? AND kind IN ({placeholders})
        """
        params = [last_metrics_id] + relevant_kinds
        with eventlog._lock:
            row = eventlog._conn.execute(query, params).fetchone()
        return row[0] > 0 if row else True
    except Exception:
        return True  # Err on side of recomputation


def write_metrics_to_db(eventlog, ias: float, gas: float, reason: str = "computed"):
    """Write updated metrics to database as metrics event."""
    try:

        meta = {
            "IAS": float(ias),
            "GAS": float(gas),
            "reason": reason,
            "component": "metrics_system",
        }
        from pmm.constants import EventKinds

        eventlog.append(EventKinds.METRICS_UPDATE, "", meta)
    except Exception:
        pass  # Don't fail if we can't write metrics


def diagnose_ias_calculation(events: List[dict]) -> dict:
    """Diagnose why IAS might be low or zero by analyzing relevant events."""
    identity_adopts = []
    autonomy_ticks = 0
    invariant_violations = 0
    identity_reflections = 0

    # Build tick mapping
    tick_index_by_eid = {}
    tick = 0
    for i, ev in enumerate(events):
        try:
            eid = int(ev.get("id") or 0)
            if eid == 0:
                eid = i + 1
        except Exception:
            eid = i + 1

        if ev.get("kind") == "autonomy_tick":
            tick += 1
        tick_index_by_eid[eid] = tick

    # Analyze events
    for i, ev in enumerate(events):
        kind = ev.get("kind")
        if kind == "identity_adopt":
            try:
                eid = int(ev.get("id") or 0)
                if eid == 0:
                    eid = i + 1
            except Exception:
                eid = i + 1
            tix = tick_index_by_eid.get(eid, 0)
            m = ev.get("meta") or {}
            name = str(
                m.get("sanitized") or m.get("name") or ev.get("content") or ""
            ).strip()
            identity_adopts.append((tix, name, eid))
        elif kind == "autonomy_tick":
            autonomy_ticks += 1
        elif kind == "invariant_violation":
            invariant_violations += 1
        elif kind == "reflection":
            txt = ev.get("content", "").lower()
            if txt and (
                ("identity" in txt and len(txt) > 20)
                or ("name" in txt and "my name" in txt)
            ):
                identity_reflections += 1

    # Calculate expected IAS
    expected_stability_bonuses = 0
    expected_penalties = 0

    if identity_adopts:
        # Sort by tick
        identity_adopts.sort(key=lambda x: x[0])

        # Check for flip-flop penalties
        for i in range(1, len(identity_adopts)):
            prev_tix, prev_name, _ = identity_adopts[i - 1]
            curr_tix, curr_name, _ = identity_adopts[i]
            if (
                curr_tix - prev_tix <= _STABLE_IDENTITY_WINDOW_TICKS
                and prev_name.lower() != curr_name.lower()
            ):
                expected_penalties += 1

        # Calculate stability bonuses from last adoption
        last_tix, last_name, _ = identity_adopts[-1]
        ticks_since_last = tick - last_tix
        stability_windows = ticks_since_last // _STABLE_IDENTITY_WINDOW_TICKS
        expected_stability_bonuses = stability_windows

    # Calculate decay factor
    decay_factor = (_DECAY_PER_TICK**autonomy_ticks) if autonomy_ticks > 0 else 1.0

    return {
        "identity_adopts": len(identity_adopts),
        "identity_adopt_details": identity_adopts,
        "autonomy_ticks": autonomy_ticks,
        "invariant_violations": invariant_violations,
        "identity_reflections": identity_reflections,
        "expected_stability_bonuses": expected_stability_bonuses,
        "expected_flip_flop_penalties": expected_penalties,
        "decay_factor": decay_factor,
        "ticks_since_last_adopt": (
            tick - identity_adopts[-1][0] if identity_adopts else 0
        ),
        "expected_ias_before_decay": (
            expected_stability_bonuses * _IAS_PER_STABLE_WINDOW
        )
        + (identity_reflections * _IAS_REFLECTION_IDENTITY_BONUS)
        - (expected_penalties * _IAS_FLIP_FLOP_PENALTY)
        - (invariant_violations * 0.005),
    }


def get_or_compute_ias_gas(eventlog) -> Tuple[float, float]:
    """Hybrid approach: read from DB first, recompute only if needed.

    This is the main function that should be used instead of compute_ias_gas
    for efficiency and consistency.
    """
    # Step 1: Try to read from database
    ias, gas, last_metrics_id = get_ias_gas_from_db(eventlog)

    if last_metrics_id > 0:
        logger.info(
            f"Read metrics from DB: IAS={ias:.3f}, GAS={gas:.3f}, event_id={last_metrics_id}"
        )
    else:
        logger.info("No metrics found in DB, will compute from scratch")

    # Step 2: Check if recomputation is needed
    # Always recompute if cached IAS is 0.0 (indicating stale data from circular dependency bug)
    force_recompute = ias == 0.0 and last_metrics_id > 0

    if needs_metrics_recomputation(eventlog, last_metrics_id) or force_recompute:
        if last_metrics_id > 0:
            if force_recompute:
                logger.info(
                    "Stale metrics detected (IAS=0.0), forcing recomputation despite no new events..."
                )
            else:
                logger.info(
                    f"New events detected after metrics_id={last_metrics_id}, recomputing..."
                )
        else:
            logger.info("Computing initial metrics from event ledger...")

        # Step 3: Recompute from events
        events = eventlog.read_all()
        old_ias, old_gas = ias, gas
        ias, gas = compute_ias_gas(events)

        logger.info(
            f"Recomputed metrics: IAS={ias:.3f} (was {old_ias:.3f}), GAS={gas:.3f} (was {old_gas:.3f})"
        )
        logger.info(
            f"These computed metrics will be sent in API headers: IAS={ias}, GAS={gas}"
        )

        # Diagnose IAS if it's unexpectedly low
        if ias < 0.01:
            diagnosis = diagnose_ias_calculation(events)
            # Calculate real-time durations (3 seconds per tick)
            tick_duration = 3.0  # seconds per autonomy_tick
            total_time = diagnosis["autonomy_ticks"] * tick_duration
            time_since_adopt = diagnosis["ticks_since_last_adopt"] * tick_duration
            window_time = _STABLE_IDENTITY_WINDOW_TICKS * tick_duration

            logger.info(
                f"IAS Diagnosis: {diagnosis['identity_adopts']} identity adoptions, "
                f"{diagnosis['autonomy_ticks']} autonomy ticks ({total_time:.0f}s total), "
                f"{diagnosis['ticks_since_last_adopt']} ticks since last adoption ({time_since_adopt:.0f}s), "
                f"{diagnosis['expected_stability_bonuses']} expected stability bonuses, "
                f"decay_factor={diagnosis['decay_factor']:.6f}"
            )
            if diagnosis["expected_stability_bonuses"] == 0:
                logger.info(
                    f"IAS=0 because: Need {_STABLE_IDENTITY_WINDOW_TICKS} ticks ({window_time:.0f}s) for first stability bonus, "
                    f"only {diagnosis['ticks_since_last_adopt']} ticks ({time_since_adopt:.0f}s) since last identity adoption"
                )

        # Step 4: Write back to database
        write_metrics_to_db(eventlog, ias, gas, "recomputed")

        # Get the new event ID for logging
        _, _, new_metrics_id = get_ias_gas_from_db(eventlog)
        logger.info(
            f"Wrote metrics to DB: IAS={ias:.3f}, GAS={gas:.3f}, event_id={new_metrics_id}"
        )
    else:
        logger.info("Metrics are current, using cached values from database")

    return ias, gas


def compute_ias_gas(events: Iterable[dict]) -> Tuple[float, float]:
    """Compute IAS (identity stability) and GAS (growth via commitments) from the ledger.

    Deterministic, event-driven rules (using constants defined above):
    - Identity stability: +0.02 per stable window of 10 autonomy ticks without re-adoption.
      Flip-flop penalty: -0.10 if a re-adopt occurs within 10 ticks of the last adoption.
    - Commitments: +0.05 GAS for novel commitment_open (not a duplicate in recent 20 ticks);
      +0.10 GAS for commitment_close; forced close penalty disabled (0.0).
    - Reflections: +0.01 IAS bonus if identity-linked; repeat penalty disabled (0.0).
    - Decay: multiply IAS and GAS by 0.9995 per autonomy_tick; floors at IAS>=0.0, GAS>=0.0.

    Clip outputs to [0.0, 1.0] for both IAS and GAS. IAS starts at 0.0 (can be zero on fresh DB).
    """
    evs: List[Dict] = list(events)  # deterministic order

    # Start from true zero - fresh DB should show 0.0, not 0.5
    ias: float = 0.0
    gas: float = 0.0

    # Map event id -> tick index and collect tick ids for window math
    tick_ids: List[int] = []
    tick_index_by_eid: Dict[int, int] = {}
    tick = 0

    # Build tick mapping with fallback for missing IDs
    for i, ev in enumerate(evs):
        try:
            eid = int(ev.get("id") or 0)
            if eid == 0:  # Fallback to index+1 for missing IDs
                eid = i + 1
        except Exception:
            eid = i + 1

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

    cons_mult = 1.0 + (conscientiousness - 0.5) * 0.3  # [0.85, 1.15] - gentler
    open_mult = 1.0 + (openness - 0.5) * 0.2  # [0.90, 1.10] - gentler

    # Tick-based novelty tracking (not count-based)
    recent_opens: List[Tuple[int, str]] = []  # (tick_index, normalized_text)
    recent_reflections: List[Tuple[int, str]] = []  # (tick_index, normalized_text)

    # Identity adoption tracking for stability windows
    adopt_events: List[Tuple[int, str]] = []  # (tick_index, name)
    last_adopt_tick: Optional[int] = None
    last_adopt_name: Optional[str] = None

    # Single pass: process events in order with proper tick-based logic
    for i, ev in enumerate(evs):
        kind = ev.get("kind")
        try:
            eid = int(ev.get("id") or 0)
            if eid == 0:
                eid = i + 1
        except Exception:
            eid = i + 1

        tix = int(tick_index_by_eid.get(eid, 0))

        if kind == "identity_adopt":
            m = ev.get("meta") or {}
            nm = str(
                m.get("sanitized") or m.get("name") or ev.get("content") or ""
            ).strip()
            confidence = float(m.get("confidence", 0.0))
            if nm and confidence >= 0.9:  # Only consider high-confidence adoptions
                adopt_events.append((tix, nm))

            # Flip-flop penalty if within the stable window
            if last_adopt_tick is not None and last_adopt_name and nm:
                if (tix - int(last_adopt_tick)) <= _STABLE_IDENTITY_WINDOW_TICKS and (
                    _norm_text(nm) != _norm_text(last_adopt_name)
                ):
                    ias -= _IAS_FLIP_FLOP_PENALTY

            # Apply incremental stability bonus for completed windows since last adoption
            if last_adopt_tick is not None:
                dt = tix - int(last_adopt_tick)
                if dt >= _STABLE_IDENTITY_WINDOW_TICKS:
                    windows = dt // _STABLE_IDENTITY_WINDOW_TICKS
                    ias += float(windows) * _IAS_PER_STABLE_WINDOW

            last_adopt_tick = tix
            last_adopt_name = nm

        elif kind == "commitment_open":
            txt = _norm_text(ev.get("content"))
            if txt:
                # Check novelty using tick-based window (not count-based)
                is_novel = True
                for past_tix, past_txt in recent_opens:
                    if txt == past_txt and (tix - past_tix) <= _OPEN_NOVEL_WINDOW_TICKS:
                        is_novel = False
                        break

                if is_novel:
                    gas += _GAS_PER_COMMIT_OPEN_NOVEL * open_mult

                # Add to recent opens (tick-based)
                recent_opens.append((tix, txt))
                # Clean old entries outside window
                recent_opens = [
                    (t, s)
                    for t, s in recent_opens
                    if (tix - t) <= _OPEN_NOVEL_WINDOW_TICKS
                ]

        elif kind == "commitment_close":
            gas += _GAS_PER_COMMIT_CLOSE_CLEAN * cons_mult

        elif kind == "commitment_expire":
            if _GAS_FORCED_CLOSE_PENALTY > 0:  # Only apply if not disabled
                gas -= _GAS_FORCED_CLOSE_PENALTY

        elif kind == "reflection":
            txt = _norm_text(ev.get("content"))
            if txt:
                # Identity-linked bonus (more restrictive check)
                if ("identity" in txt and len(txt) > 20) or (
                    "name" in txt and "my name" in txt
                ):
                    ias += _IAS_REFLECTION_IDENTITY_BONUS

                # Repetition penalty (only if enabled and tick-based)
                if _GAS_REFLECTION_REPEAT_PENALTY > 0:
                    for past_tix, past_txt in recent_reflections:
                        if (
                            txt == past_txt
                            and (tix - past_tix) <= _REPEAT_REFLECT_WINDOW_TICKS
                        ):
                            gas -= _GAS_REFLECTION_REPEAT_PENALTY
                            break

                # Add to recent reflections (tick-based)
                recent_reflections.append((tix, txt))
                # Clean old entries outside window
                recent_reflections = [
                    (t, s)
                    for t, s in recent_reflections
                    if (tix - t) <= _REPEAT_REFLECT_WINDOW_TICKS
                ]

        elif kind == "invariant_violation":
            ias -= 0.005  # Much gentler penalty (was 0.02)
            gas -= 0.005  # Much gentler penalty (was 0.02)

        elif kind == "autonomy_tick":
            # Apply decay
            ias *= _DECAY_PER_TICK
            gas *= _DECAY_PER_TICK

            # Apply stability bonus incrementally every 10 ticks after identity adoption
            if adopt_events:
                last_tix, _ = adopt_events[-1]
                dt = tix - last_tix
                # Award stability bonus every 10th tick after adoption
                if dt > 0 and dt % _STABLE_IDENTITY_WINDOW_TICKS == 0:
                    ias += _IAS_PER_STABLE_WINDOW

    # Clip to valid ranges - IAS can now be 0.0 on fresh DB
    ias = _clip(ias, 0.0, 1.0)
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
        from pmm.constants import EventKinds

        with eventlog._lock:
            row = eventlog._conn.execute(
                "SELECT meta FROM events WHERE kind=? ORDER BY id DESC LIMIT 1",
                (EventKinds.METRICS_UPDATE,),
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
        from pmm.constants import EventKinds

        eventlog.append(
            EventKinds.METRICS_UPDATE,
            "",
            {"GAS": new_gas, "IAS": ias_prev, "gas_delta": delta, "reason": reason},
        )
    except Exception:
        pass
    return new_gas
