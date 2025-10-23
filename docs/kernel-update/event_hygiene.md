# Event Hygiene and Idempotency Guarantees

This document outlines the guarantees and patterns for event emissions in the Persistent Mind Model (PMM) project, specifically for `policy_update`, `trait_update`, and `identity_adjust_proposal` events. The goal is to ensure auditability, determinism, and idempotency in the event log.

## General Principles

- **Idempotency**: Events should not be duplicated if they represent the same state or change. Use digest or equality checks to prevent redundant emissions.
- **Auditability**: Each event must clearly represent a state change or decision, with metadata providing context for why and when it was emitted.
- **Determinism**: Event emission logic must be reproducible from the ledger state and code, avoiding external dependencies like runtime clocks (beyond timestamps recorded in the ledger).

## Event-Specific Guarantees

### `policy_update`

- **When to Append**: Emit only when a policy parameter (e.g., reflection cadence) changes due to a stage transition or explicit update. For reflection policies, emit exactly once per stage change, even if parameters match historical values for that stage.
- **Deduplication**: Do not re-emit if the stage remains unchanged and parameters are identical to the last `policy_update` for the same component. Check the last event of this kind for equality in `meta.params` and `meta.component`.
- **Metadata**: Include `component`, `params`, and `stage` (if applicable) in `meta` to provide context for the policy change.

### `trait_update`

- **When to Append**: Emit when a trait value changes, either due to self-evolution policies, kernel proposals, or ratcheting mechanisms.
- **Deduplication**: Compare the proposed change against the last `trait_update` for the same trait(s). If the delta or target value is identical, suppress the event. Use a digest of `meta.changes` or `meta.trait` and `meta.delta` for comparison.
- **Metadata**: Include `trait` (or `changes` for multiple traits), `delta`, `target` (if applicable), and `reason` in `meta` to explain the adjustment.

### `identity_adjust_proposal`

- **When to Append**: Emit when the `EvolutionKernel` proposes an identity adjustment (trait or name change) based on evaluation of commitments and metrics.
- **Deduplication**: Suppress if the proposal matches the last `identity_adjust_proposal` in terms of `traits` and `context` (e.g., IAS/GAS values, adoption count). Use a digest of the proposal content for quick comparison.
- **Metadata**: Include `traits`, `context` (adoption history, metrics), and `reason` in `meta` to provide a clear rationale for the proposal.

## Deduplication Pattern

The autonomy loop in `loop.py` already implements a deduplication pattern to avoid redundant events. This pattern should be standardized across all emitters:

```python
# Example deduplication check before appending an event
def should_emit_event(eventlog, kind, meta):
    last_events = eventlog.read_tail(limit=10)  # Adjust limit based on context
    for ev in reversed(last_events):
        if ev.get('kind') == kind:
            last_meta = ev.get('meta', {})
            if are_meta_equal(last_meta, meta):  # Implement equality check or digest
                return False  # Suppress duplicate
            break
    return True  # Emit if no duplicate found

def are_meta_equal(meta1, meta2):
    # Compare relevant fields or compute a digest for complex structures
    return compute_digest(meta1) == compute_digest(meta2)

def compute_digest(meta):
    import json, hashlib
    return hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()
```

This pattern ensures that events are only appended when they represent a new state or decision, maintaining a clean and auditable ledger.
