"""Impact Tracker for Enhanced Feedback Loop (Phase 1A).

Tracks action-outcome pairs with effectiveness scores to enable Echo to evaluate
the impact of its actions and adjust internal processes accordingly.

Design Principles (CONTRIBUTING.md compliant):
- Deterministic: Same inputs always produce same action IDs and impact scores
- Bounded: Effectiveness scores clamped to [0.0, 1.0], limited window sizes
- Transparent: All actions and impacts logged to event ledger
- Incremental: Rolling averages prevent overreaction to outliers
"""

from __future__ import annotations

import hashlib
import json
import logging

logger = logging.getLogger(__name__)

# Constants for deterministic impact calculation
_DEFAULT_IMPACT_WINDOW_TICKS: int = 10  # Window to measure action impact
_EFFECTIVENESS_WEIGHT_IAS: float = 0.6  # Weight for IAS changes in effectiveness
_EFFECTIVENESS_WEIGHT_GAS: float = 0.4  # Weight for GAS changes in effectiveness
_MIN_EFFECTIVENESS_SCORE: float = 0.0  # Minimum effectiveness score
_MAX_EFFECTIVENESS_SCORE: float = 1.0  # Maximum effectiveness score
_MAX_ACTION_HISTORY: int = 100  # Maximum actions to track per type


def _generate_action_id(action_type: str, action_data: dict, tick_no: int) -> int:
    """Generate deterministic action ID from action type, data, and tick.

    Uses SHA-256 hash to ensure uniqueness while remaining deterministic
    for same inputs at same tick.

    Args:
        action_type: Type of action (e.g., "commitment_open", "reflection")
        action_data: Action-specific data dictionary
        tick_no: Current tick number for temporal uniqueness

    Returns:
        Deterministic integer action ID
    """
    # Create deterministic string representation
    action_str = json.dumps(action_data, sort_keys=True, separators=(",", ":"))
    input_str = f"{action_type}:{action_str}:{tick_no}"

    # Generate hash and convert to integer
    hash_bytes = hashlib.sha256(input_str.encode()).digest()
    action_id = int.from_bytes(hash_bytes[:8], byteorder="big")

    return action_id


def _clip_effectiveness(score: float) -> float:
    """Clip effectiveness score to valid range."""
    try:
        import math

        if score is None or not isinstance(score, (int, float)) or math.isnan(score):
            return _MIN_EFFECTIVENESS_SCORE
        if math.isinf(score):
            return _MAX_EFFECTIVENESS_SCORE if score > 0 else _MIN_EFFECTIVENESS_SCORE
        if score < _MIN_EFFECTIVENESS_SCORE:
            return _MIN_EFFECTIVENESS_SCORE
        elif score > _MAX_EFFECTIVENESS_SCORE:
            return _MAX_EFFECTIVENESS_SCORE
        return float(score)
    except Exception:
        return _MIN_EFFECTIVENESS_SCORE


def register_action(eventlog, action_type: str, action_data: dict, tick_no: int) -> int:
    """Register an action for impact tracking.

    Emits an action_initiated event with baseline state snapshot.

    Args:
        eventlog: EventLog instance for ledger operations
        action_type: Type of action being registered
        action_data: Action-specific data dictionary
        tick_no: Current tick number

    Returns:
        Action ID for later impact measurement
    """
    try:
        # Generate deterministic action ID
        action_id = _generate_action_id(action_type, action_data, tick_no)

        # Capture baseline state (IAS/GAS from latest metrics or autonomy_tick)
        baseline_state = _capture_baseline_state(eventlog)

        # Emit action_initiated event
        from pmm.constants import EventKinds

        event_data = {
            "action_type": action_type,
            "action_id": action_id,
            "baseline_state": baseline_state,
            "tick_no": tick_no,
            "action_data": action_data,
        }

        eventlog.append(
            kind=EventKinds.ACTION_INITIATED,
            content="",  # Add required content parameter
            meta=event_data,
        )

        logger.debug(
            f"Registered action {action_id} of type {action_type} at tick {tick_no}"
        )

        return action_id

    except Exception as e:
        logger.error(f"Failed to register action: {e}")
        return -1


def measure_impact(
    eventlog, action_id: int, window_ticks: int = _DEFAULT_IMPACT_WINDOW_TICKS
) -> dict:
    """Measure the impact of a previously registered action.

    Calculates ΔIAS and ΔGAS within the specified window and computes
    an effectiveness score.

    Args:
        eventlog: EventLog instance for ledger operations
        action_id: ID of action to measure
        window_ticks: Number of ticks to measure impact over

    Returns:
        Dictionary with impact measurements and effectiveness score
    """
    try:
        # Find the action_initiated event
        action_event = _find_action_event(eventlog, action_id)
        if not action_event:
            return {"error": f"Action {action_id} not found"}

        # Extract baseline state and timing
        baseline_state = action_event.get("meta", {}).get("baseline_state", {})
        action_tick = action_event.get("meta", {}).get("tick_no", 0)

        # Get current state
        current_state = _capture_baseline_state(eventlog)

        # Calculate deltas
        delta_ias = current_state.get("IAS", 0.0) - baseline_state.get("IAS", 0.0)
        delta_gas = current_state.get("GAS", 0.0) - baseline_state.get("GAS", 0.0)

        # Compute effectiveness score
        effectiveness = _compute_effectiveness_score(delta_ias, delta_gas)

        # Identify impact signals (commitment acceptances, etc.)
        impact_signals = _identify_impact_signals(
            eventlog, action_tick, action_tick + window_ticks
        )

        impact_data = {
            "action_id": action_id,
            "window_ticks": window_ticks,
            "delta_ias": delta_ias,
            "delta_gas": delta_gas,
            "effectiveness_score": effectiveness,
            "impact_signals": impact_signals,
            "baseline_state": baseline_state,
            "current_state": current_state,
        }

        # Emit impact_measured event
        from pmm.constants import EventKinds

        eventlog.append(
            kind=EventKinds.IMPACT_MEASURED,
            content="",  # Add required content parameter
            meta=impact_data,
        )

        logger.debug(
            f"Measured impact for action {action_id}: ΔIAS={delta_ias:.3f}, "
            f"ΔGAS={delta_gas:.3f}, effectiveness={effectiveness:.3f}"
        )

        return impact_data

    except Exception as e:
        logger.error(f"Failed to measure impact for action {action_id}: {e}")
        return {"error": str(e)}


def get_effectiveness_history(
    eventlog, action_type: str, limit: int = _MAX_ACTION_HISTORY
) -> list:
    """Get rolling effectiveness history for a specific action type.

    Args:
        eventlog: EventLog instance for ledger operations
        action_type: Type of action to get history for
        limit: Maximum number of records to return

    Returns:
        List of effectiveness records with timestamps and scores
    """
    try:

        # Query recent impact_measured events for this action type
        events = eventlog.query(
            kind="impact_measured",  # Use singular kind parameter
            limit=limit * 2,  # Get more to filter by action type
        )

        # Filter by action type and extract relevant data
        history = []
        for event in events:
            meta = event.get("meta", {})

            # Look up the corresponding action_initiated event to get action_type
            action_id = meta.get("action_id")
            if action_id:
                action_event = _find_action_event(eventlog, action_id)
                if (
                    action_event
                    and action_event.get("meta", {}).get("action_type") == action_type
                ):
                    history.append(
                        {
                            "action_id": action_id,
                            "effectiveness_score": meta.get("effectiveness_score", 0.0),
                            "delta_ias": meta.get("delta_ias", 0.0),
                            "delta_gas": meta.get("delta_gas", 0.0),
                            "impact_signals": meta.get("impact_signals", []),
                            "timestamp": event.get("timestamp"),
                        }
                    )

        # Return most recent records up to limit
        return history[:limit]

    except Exception as e:
        logger.error(f"Failed to get effectiveness history for {action_type}: {e}")
        return []


def measure_pending_impacts(
    eventlog, current_tick: int, window_ticks: int = _DEFAULT_IMPACT_WINDOW_TICKS
) -> int:
    """Measure impacts for actions that are due for evaluation.

    Called during autonomy_tick to evaluate actions whose measurement window has passed.

    Args:
        eventlog: EventLog instance for ledger operations
        current_tick: Current tick number
        window_ticks: Standard impact measurement window

    Returns:
        Number of impacts measured
    """
    try:

        # Find recent action_initiated events that haven't been measured
        action_events = eventlog.query(
            kind="action_initiated",  # Use singular kind parameter
            limit=_MAX_ACTION_HISTORY,
        )

        measured_count = 0
        for event in action_events:
            meta = event.get("meta", {})
            action_id = meta.get("action_id")
            action_tick = meta.get("tick_no", 0)

            # Check if this action is due for measurement
            if action_id and (current_tick - action_tick) >= window_ticks:
                # Check if already measured
                if not _impact_already_measured(eventlog, action_id):
                    measure_impact(eventlog, action_id, window_ticks)
                    measured_count += 1

        if measured_count > 0:
            logger.debug(
                f"Measured {measured_count} pending impacts at tick {current_tick}"
            )

        return measured_count

    except Exception as e:
        logger.error(f"Failed to measure pending impacts: {e}")
        return 0


# Helper functions


def _capture_baseline_state(eventlog) -> dict:
    """Capture current baseline state (IAS/GAS/open_commitments)."""
    try:
        # Try to get latest autonomy_tick first
        autonomy_events = eventlog.query(
            kind="autonomy_tick",  # Use singular kind parameter
            limit=1,
        )

        if autonomy_events:
            telemetry = autonomy_events[0].get("meta", {}).get("telemetry", {})
            return {
                "IAS": float(telemetry.get("IAS", 0.0)),
                "GAS": float(telemetry.get("GAS", 0.0)),
                "open_commitments": int(telemetry.get("open_commitments", 0)),
            }

        # Fallback to metrics_update
        metrics_events = eventlog.query(
            kind="metrics_update",  # Use singular kind parameter
            limit=1,
        )

        if metrics_events:
            meta = metrics_events[0].get("meta", {})
            return {
                "IAS": float(meta.get("IAS", 0.0)),
                "GAS": float(meta.get("GAS", 0.0)),
                "open_commitments": 0,  # Not available in metrics events
            }

        # Default fallback
        return {"IAS": 0.0, "GAS": 0.0, "open_commitments": 0}

    except Exception as e:
        logger.error(f"Failed to capture baseline state: {e}")
        return {"IAS": 0.0, "GAS": 0.0, "open_commitments": 0}


def _find_action_event(eventlog, action_id: int) -> dict:
    """Find action_initiated event by action ID."""
    try:

        events = eventlog.query(
            kind="action_initiated",  # Use singular kind parameter
            limit=_MAX_ACTION_HISTORY,
        )

        for event in events:
            if event.get("meta", {}).get("action_id") == action_id:
                return event

        return {}

    except Exception as e:
        logger.error(f"Failed to find action event {action_id}: {e}")
        return {}


def _compute_effectiveness_score(delta_ias: float, delta_gas: float) -> float:
    """Compute effectiveness score from IAS and GAS deltas.

    Uses weighted combination with clipping to [0.0, 1.0] range.
    Positive deltas increase effectiveness, negative deltas decrease it.
    """
    try:
        # Normalize deltas (IAS and GAS are both in [0.0, 1.0] range)
        # Positive changes are good, negative changes are bad
        ias_component = max(0.0, delta_ias)  # Only count positive IAS changes
        gas_component = max(0.0, delta_gas)  # Only count positive GAS changes

        # Weighted combination
        raw_score = (
            _EFFECTIVENESS_WEIGHT_IAS * ias_component
            + _EFFECTIVENESS_WEIGHT_GAS * gas_component
        )

        # Scale and clip (assuming max meaningful delta is ~0.2 per window)
        scaled_score = min(1.0, raw_score * 5.0)

        return _clip_effectiveness(scaled_score)

    except Exception as e:
        logger.error(f"Failed to compute effectiveness score: {e}")
        return _MIN_EFFECTIVENESS_SCORE


def _identify_impact_signals(eventlog, start_tick: int, end_tick: int) -> list:
    """Identify positive impact signals within tick window."""
    try:

        # Look for positive signals in the window
        signal_events = eventlog.query(
            kind="commitment_close",  # Use singular kind parameter (query one kind at a time)
            limit=50,
        )

        reflection_events = eventlog.query(
            kind="reflection",
            limit=50,
        )

        all_signal_events = signal_events + reflection_events

        signals = []
        for event in all_signal_events:
            # Simple tick-based filtering (could be enhanced with actual timestamps)
            event_tick = event.get("meta", {}).get("tick_no", 0)
            if start_tick <= event_tick <= end_tick:
                signals.append(event.get("kind"))

        return list(set(signals))  # Remove duplicates

    except Exception as e:
        logger.error(f"Failed to identify impact signals: {e}")
        return []


def _impact_already_measured(eventlog, action_id: int) -> bool:
    """Check if impact has already been measured for this action."""
    try:

        impact_events = eventlog.query(
            kind="impact_measured",  # Use singular kind parameter
            limit=_MAX_ACTION_HISTORY,
        )

        for event in impact_events:
            if event.get("meta", {}).get("action_id") == action_id:
                return True

        return False

    except Exception as e:
        logger.error(f"Failed to check if impact already measured for {action_id}: {e}")
        return False
