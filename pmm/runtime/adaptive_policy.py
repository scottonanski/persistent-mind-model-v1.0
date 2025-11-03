"""Adaptive Policy for Enhanced Feedback Loop (Phase 1B).

Translates impact insights into bounded parameter adjustments to enable
Echo to adapt its internal processes based on action effectiveness.

Design Principles (CONTRIBUTING.md compliant):
- Deterministic: Same impact data → same adaptations
- Bounded: All adjustments clamped to safe ranges (±10% per cycle)
- Transparent: All adaptations logged with full reasoning
- Incremental: Gradual changes to prevent system instability
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Constants for deterministic adaptation calculations
_MAX_ADJUSTMENT_PERCENT: float = 0.10  # Maximum 10% adjustment per cycle
_MIN_ADJUSTMENT_PERCENT: float = -0.10  # Minimum -10% adjustment per cycle
_EFFECTIVENESS_THRESHOLD_HIGH: float = 0.8  # High effectiveness threshold
_EFFECTIVENESS_THRESHOLD_LOW: float = 0.3  # Low effectiveness threshold
_MIN_HISTORY_FOR_ADAPTATION: int = 3  # Minimum samples needed for adaptation
_MAX_ADAPTATION_FREQUENCY: int = 5  # Max adaptations per 10 ticks
_ADAPTATION_DECAY_FACTOR: float = 0.95  # Decay factor for gradual reversion

# Component-specific adjustment parameters
_COMPONENTS = {
    "reflection_policy": {
        "cadence_multiplier": {"min": 0.5, "max": 2.0, "default": 1.0},
        "novelty_threshold": {"min": 0.01, "max": 0.15, "default": 0.05},
        "depth_requirement": {"min": 0.1, "max": 0.9, "default": 0.5},
    },
    "commitment_policy": {
        "priority_weight": {"min": 0.5, "max": 2.0, "default": 1.0},
        "acceptance_threshold": {"min": 0.3, "max": 0.9, "default": 0.6},
        "ttl_multiplier": {"min": 0.8, "max": 1.5, "default": 1.0},
    },
    "trait_evolution": {
        "learning_rate": {"min": 0.01, "max": 0.2, "default": 0.05},
        "stability_bonus": {"min": 0.01, "max": 0.1, "default": 0.03},
        "decay_resistance": {"min": 0.99, "max": 0.999, "default": 0.995},
    },
}


def _clip_adjustment(value: float, current: float, bounds: dict) -> float:
    """Clip adjustment to safe range."""
    try:
        max_val = bounds["max"]
        min_val = bounds["min"]

        # Calculate maximum allowed change
        max_change = abs(current) * _MAX_ADJUSTMENT_PERCENT
        min_change = -abs(current) * _MAX_ADJUSTMENT_PERCENT

        # Apply adjustment
        new_value = current + value

        # Clip to bounds and change limits
        if value > 0:
            new_value = min(new_value, current + max_change, max_val)
        else:
            new_value = max(new_value, current + min_change, min_val)

        return new_value

    except Exception as e:
        logger.error(f"Failed to clip adjustment: {e}")
        return current


def _compute_adaptation_strength(effectiveness_scores: list[float]) -> float:
    """Compute adaptation strength based on effectiveness history.

    Args:
        effectiveness_scores: List of recent effectiveness scores

    Returns:
        Adaptation strength in range [-0.1, 0.1]
    """
    try:
        if not effectiveness_scores:
            return 0.0

        # Calculate average effectiveness
        avg_effectiveness = sum(effectiveness_scores) / len(effectiveness_scores)

        # Determine adaptation direction and strength
        if avg_effectiveness >= _EFFECTIVENESS_THRESHOLD_HIGH:
            # High effectiveness - positive reinforcement (smaller adjustments)
            strength = (
                0.05
                * (avg_effectiveness - _EFFECTIVENESS_THRESHOLD_HIGH)
                / (1.0 - _EFFECTIVENESS_THRESHOLD_HIGH)
            )
        elif avg_effectiveness <= _EFFECTIVENESS_THRESHOLD_LOW:
            # Low effectiveness - corrective adjustment
            strength = -0.10 * (1.0 - avg_effectiveness / _EFFECTIVENESS_THRESHOLD_LOW)
        else:
            # Moderate effectiveness - minimal adjustment
            strength = 0.01 * (avg_effectiveness - 0.5) / 0.5

        # Clip to allowed range
        return max(_MIN_ADJUSTMENT_PERCENT, min(_MAX_ADJUSTMENT_PERCENT, strength))

    except Exception as e:
        logger.error(f"Failed to compute adaptation strength: {e}")
        return 0.0


def _get_current_policy_state(eventlog) -> dict:
    """Get current policy state from recent adaptation_applied events."""
    try:

        adaptation_events = eventlog.query(kind="adaptation_applied", limit=50)

        current_state = {}

        # Initialize with defaults
        for component, params in _COMPONENTS.items():
            current_state[component] = {}
            for param_name, param_config in params.items():
                current_state[component][param_name] = param_config["default"]

        # Apply recent adaptations in order
        for event in adaptation_events:
            meta = event.get("meta", {})
            component = meta.get("component")
            adjustments = meta.get("adjustments", {})

            if component in current_state:
                current_state[component].update(adjustments)

        return current_state

    except Exception as e:
        logger.error(f"Failed to get current policy state: {e}")
        # Return defaults on error
        return {
            component: {param: config["default"] for param, config in params.items()}
            for component, params in _COMPONENTS.items()
        }


def _should_adapt(eventlog, component: str) -> bool:
    """Check if component should be adapted based on frequency limits."""
    try:

        # Get recent adaptation events for this component
        adaptation_events = eventlog.query(kind="adaptation_applied", limit=100)

        # Count adaptations for this component in recent events
        component_adaptations = [
            ev
            for ev in adaptation_events
            if ev.get("meta", {}).get("component") == component
        ]

        # Check if we've exceeded frequency limit
        return len(component_adaptations) < _MAX_ADAPTATION_FREQUENCY

    except Exception as e:
        logger.error(f"Failed to check adaptation frequency: {e}")
        return False  # Conservative: don't adapt if unsure


def compute_adaptations(eventlog, impact_data: dict) -> dict:
    """Compute parameter adjustments based on impact data.

    Args:
        eventlog: EventLog instance for ledger operations
        impact_data: Dictionary with impact measurements and effectiveness scores

    Returns:
        Dictionary with computed adaptations
    """
    try:
        adaptations = {}
        reasoning = []

        # Get effectiveness history by action type
        action_types = ["commitment_open", "reflection", "identity_adopt"]

        for action_type in action_types:
            from pmm.runtime.impact_tracker import get_effectiveness_history

            history = get_effectiveness_history(eventlog, action_type, limit=10)

            if len(history) >= _MIN_HISTORY_FOR_ADAPTATION:
                effectiveness_scores = [h["effectiveness_score"] for h in history]
                avg_score = sum(effectiveness_scores) / len(effectiveness_scores)

                # Compute adaptation strength
                strength = _compute_adaptation_strength(effectiveness_scores)

                # Map action types to components
                if action_type == "commitment_open":
                    component = "commitment_policy"
                    if strength > 0:
                        adaptations["commitment_policy"] = adaptations.get(
                            "commitment_policy", {}
                        )
                        # High effectiveness: increase acceptance threshold (more selective)
                        current = _get_current_policy_state(eventlog)[
                            "commitment_policy"
                        ]["acceptance_threshold"]
                        new_val = _clip_adjustment(
                            strength * 0.1,
                            current,
                            _COMPONENTS["commitment_policy"]["acceptance_threshold"],
                        )
                        adaptations["commitment_policy"][
                            "acceptance_threshold"
                        ] = new_val
                        reasoning.append(
                            f"High commitment effectiveness ({avg_score:.2f}): increasing selectivity"
                        )
                    else:
                        adaptations["commitment_policy"] = adaptations.get(
                            "commitment_policy", {}
                        )
                        # Low effectiveness: decrease acceptance threshold (more permissive)
                        current = _get_current_policy_state(eventlog)[
                            "commitment_policy"
                        ]["acceptance_threshold"]
                        new_val = _clip_adjustment(
                            strength * 0.1,
                            current,
                            _COMPONENTS["commitment_policy"]["acceptance_threshold"],
                        )
                        adaptations["commitment_policy"][
                            "acceptance_threshold"
                        ] = new_val
                        reasoning.append(
                            f"Low commitment effectiveness ({avg_score:.2f}): increasing permissiveness"
                        )

                elif action_type == "reflection":
                    component = "reflection_policy"
                    if abs(strength) > 0.01:  # Only adapt if significant
                        adaptations["reflection_policy"] = adaptations.get(
                            "reflection_policy", {}
                        )
                        if strength > 0:
                            # High effectiveness: increase cadence (more frequent)
                            current = _get_current_policy_state(eventlog)[
                                "reflection_policy"
                            ]["cadence_multiplier"]
                            new_val = _clip_adjustment(
                                strength * 0.2,
                                current,
                                _COMPONENTS["reflection_policy"]["cadence_multiplier"],
                            )
                            adaptations["reflection_policy"][
                                "cadence_multiplier"
                            ] = new_val
                            reasoning.append(
                                f"High reflection effectiveness ({avg_score:.2f}): increasing cadence"
                            )
                        else:
                            # Low effectiveness: decrease novelty threshold (easier to trigger)
                            current = _get_current_policy_state(eventlog)[
                                "reflection_policy"
                            ]["novelty_threshold"]
                            new_val = _clip_adjustment(
                                abs(strength) * -0.5,
                                current,
                                _COMPONENTS["reflection_policy"]["novelty_threshold"],
                            )
                            adaptations["reflection_policy"][
                                "novelty_threshold"
                            ] = new_val
                            reasoning.append(
                                f"Low reflection effectiveness ({avg_score:.2f}): lowering novelty threshold"
                            )

        # Apply gradual decay to prevent drift
        current_state = _get_current_policy_state(eventlog)
        for component, params in current_state.items():
            if component not in adaptations:
                adaptations[component] = {}

            for param_name, current_value in params.items():
                if param_name not in adaptations[component]:
                    # Gradual decay toward default
                    default_val = _COMPONENTS[component][param_name]["default"]
                    decayed_val = (
                        current_value * _ADAPTATION_DECAY_FACTOR
                        + default_val * (1 - _ADAPTATION_DECAY_FACTOR)
                    )
                    adaptations[component][param_name] = decayed_val

        return {
            "adaptations": adaptations,
            "reasoning": reasoning,
            "based_on_impact_ids": impact_data.get("impact_ids", []),
            "strength": strength if "strength" in locals() else 0.0,
        }

    except Exception as e:
        logger.error(f"Failed to compute adaptations: {e}")
        return {
            "adaptations": {},
            "reasoning": [f"Error computing adaptations: {e}"],
            "based_on_impact_ids": [],
            "strength": 0.0,
        }


def apply_parameter_adjustments(eventlog, adaptations: dict) -> bool:
    """Apply computed parameter adjustments to the system.

    Emits an adaptation_applied event with full audit trail.

    Args:
        eventlog: EventLog instance for ledger operations
        adaptations: Dictionary with computed adaptations

    Returns:
        True if adaptations were applied successfully
    """
    try:
        from pmm.constants import EventKinds

        adaptation_data = adaptations.get("adaptations", {})
        reasoning = adaptations.get("reasoning", [])
        based_on_impact_ids = adaptations.get("based_on_impact_ids", [])
        strength = adaptations.get("strength", 0.0)

        if not adaptation_data:
            logger.debug("No adaptations to apply")
            return False

        # Emit adaptation_applied event
        event_data = {
            "component": (
                "multiple"
                if len(adaptation_data) > 1
                else next(iter(adaptation_data.keys()))
            ),
            "adjustments": adaptation_data,
            "based_on_impact_ids": based_on_impact_ids,
            "reason": (
                "; ".join(reasoning) if reasoning else "Adaptive policy adjustment"
            ),
            "strength": strength,
        }

        eventlog.append(
            kind=EventKinds.ADAPTATION_APPLIED,
            content="",  # Required content parameter
            meta=event_data,
        )

        logger.info(
            f"Applied adaptive policy adjustments: {adaptation_data} "
            f"(strength: {strength:.3f}, reasons: {len(reasoning)})"
        )

        return True

    except Exception as e:
        logger.error(f"Failed to apply parameter adjustments: {e}")
        return False


def compute_and_apply_adaptations(eventlog) -> bool:
    """Compute and apply adaptations based on recent impact data.

    Convenience function that combines compute_adaptations and apply_parameter_adjustments.

    Args:
        eventlog: EventLog instance for ledger operations

    Returns:
        True if adaptations were applied
    """
    try:
        # Get recent impact data

        impact_events = eventlog.query(kind="impact_measured", limit=20)

        if not impact_events:
            return False  # No impact data to base adaptations on

        # Extract impact IDs for reasoning
        impact_ids = [
            ev.get("meta", {}).get("action_id")
            for ev in impact_events
            if ev.get("meta", {}).get("action_id")
        ]

        impact_data = {"impact_ids": impact_ids}

        # Compute adaptations
        adaptations = compute_adaptations(eventlog, impact_data)

        # Apply adaptations
        return apply_parameter_adjustments(eventlog, adaptations)

    except Exception as e:
        logger.error(f"Failed to compute and apply adaptations: {e}")
        return False


def get_adaptation_history(eventlog, limit: int = 100) -> list:
    """Get recent adaptation history.

    Args:
        eventlog: EventLog instance for ledger operations
        limit: Maximum number of records to return

    Returns:
        List of adaptation records with timestamps and details
    """
    try:

        events = eventlog.query(kind="adaptation_applied", limit=limit)

        history = []
        for event in events:
            meta = event.get("meta", {})
            history.append(
                {
                    "component": meta.get("component"),
                    "adjustments": meta.get("adjustments", {}),
                    "reason": meta.get("reason", ""),
                    "strength": meta.get("strength", 0.0),
                    "based_on_impact_ids": meta.get("based_on_impact_ids", []),
                    "timestamp": event.get("timestamp"),
                }
            )

        return history

    except Exception as e:
        logger.error(f"Failed to get adaptation history: {e}")
        return []


def get_current_parameters(eventlog) -> dict:
    """Get current parameter values after all adaptations.

    Args:
        eventlog: EventLog instance for ledger operations

    Returns:
        Dictionary with current parameter values
    """
    try:
        return _get_current_policy_state(eventlog)
    except Exception as e:
        logger.error(f"Failed to get current parameters: {e}")
        return {}
