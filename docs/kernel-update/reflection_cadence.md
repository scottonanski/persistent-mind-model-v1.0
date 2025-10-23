# Reflection Cadence Source of Truth

This document establishes the single source of truth for reflection cadence policies in the Persistent Mind Model (PMM) project.

## Source of Truth

- **Location**: The `CADENCE_BY_STAGE` dictionary in `pmm/runtime/loop.py` (lines 209-214) is the definitive source for stage-aware reflection cadence policies.
- **Purpose**: This dictionary defines the minimum turns (`min_turns`), minimum time in seconds (`min_time_s`), and whether to force reflection if stuck (`force_reflect_if_stuck`) for each stage (S0 to S4).
- **Contract**: All components determining reflection cadence must reference `CADENCE_BY_STAGE` to ensure consistency across the runtime. This central configuration avoids duplicated or conflicting cadence logic.

```python
# Excerpt from pmm/runtime/loop.py (lines 209-214)
CADENCE_BY_STAGE = {
    "S0": {"min_turns": 2, "min_time_s": 20, "force_reflect_if_stuck": True},
    "S1": {"min_turns": 3, "min_time_s": 35, "force_reflect_if_stuck": True},
    "S2": {"min_turns": 4, "min_time_s": 50, "force_reflect_if_stuck": False},
    "S3": {"min_turns": 5, "min_time_s": 70, "force_reflect_if_stuck": False},
    "S4": {"min_turns": 6, "min_time_s": 90, "force_reflect_if_stuck": False},
}
```

## Rationale for Overrides

- **Policy Overrides**: In cases where a `policy_update` event with `component='reflection'` exists in the event log, it may override the default cadence values from `CADENCE_BY_STAGE`. This is handled in functions like `_resolve_reflection_policy_overrides` (lines 319-337 in `loop.py`). Such overrides are temporary and tied to specific stage transitions or policy adjustments, ensuring they are auditable via the event log.
- **Why Overrides Exist**: Overrides allow dynamic adaptation of reflection cadence based on runtime state or stage progression, but they must always be explicitly recorded as events to maintain transparency and determinism.

## Usage

- All runtime components (e.g., `AutonomyLoop`, `ReflectionCooldown`) should read cadence values from `CADENCE_BY_STAGE` or the latest `policy_update` event if applicable, ensuring a unified approach to reflection timing.
