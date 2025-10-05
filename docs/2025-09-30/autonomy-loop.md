# Autonomy Loop

The autonomy loop is PMM’s background heartbeat. A daemon thread wakes up on a fixed cadence
(default `60` seconds in `AutonomyLoop.__init__`, though the CLI configures it to `10` seconds)
and runs the following pipeline:

1. **Snapshot pull** – reuse the cached `LedgerSnapshot` from the runtime when available.
2. **Subsystem pass (AutonomousSystemsManager)** – trait drift, stage behaviour manager,
   emergence scorer, adaptive cadence, and commitment health all inspect the recent events
   (the loop already gathered them so we avoid repeated `read_all()` calls).
3. **Reflection decision** – `ReflectionCooldown` enforces three deterministic gates:
   minimum turns (`min_turns`, default `2`), minimum wall clock (`min_seconds`, default `60`),
   and novelty threshold (policy‐driven, default `0.2`). If any gate fails we append
   `reflection_skipped` with the reason.
4. **Reflection emission** – if cadence gates allow it we call `emit_reflection(...)`.
   The reflection goes through the same acceptance gate the user path uses. If the model
   returns text that is too short/empty/policy-loop-y we deterministically fall back to
   `generate_system_status_reflection(...)`, guaranteeing we still emit a `reflection`
   event even on the first autonomy tick.
5. **Telemetry** – the loop appends an `autonomy_tick` event with IAS/GAS, stage, and the
   subsystems that ran so we can inspect the cycle after the fact.

Each tick therefore leaves an auditable trace: the subsystem decisions, any reflections
or policy updates, and the final `autonomy_tick` with the telemetry snapshot.

> The implementation lives in `pmm/runtime/loop.py` (`AutonomyLoop` and friends).

---

## Subsystems touched each tick

PMM wraps the subsystems in `AutonomousSystemsManager` (`pmm/runtime/autonomy_integration.py`).
For each tick the manager:

- Runs **TraitDriftManager** to nudge OCEAN traits when commitments complete.
- Invokes **StageBehaviorManager** to surface stage-specific policy hints.
- Calls **EmergenceManager** for composite IAS/GAS/commitment metrics.
- Uses **AdaptiveReflectionCadence** to feed cadence hints to the cooldown.
- Computes commitment health via **ProactiveCommitmentManager**.

All of the above operate on the event window the loop already cached; we do not rescan
SQLite from scratch for each subsystem.

---

## Reflection acceptance & fallback

`emit_reflection` (in `pmm/runtime/loop.py`) is shared by the user and autonomy paths.
Important details:

- The raw text is checked against `pmm/runtime/reflector.accept`. Rejections append a
  `reflection_rejected` event with the reason and telemetry.
- When the rejection reason is `too_short`, `empty_reflection`, or `policy_loop_detected`
  we fall back to `generate_system_status_reflection(...)`. This produces a deterministic
  two-line reflection (`Action:` / `Why-mechanics:`) so autonomy ticks still progress.
- The reflection metadata mirrors the text (`meta["text"]`) and stores the quality score
  used by the stage pipeline.

---

## Telemetry emitted per tick

An autonomy tick typically generates:

```
["reflection" | "reflection_skipped" | "reflection_rejected"],
trait_update/policy_update events if subsystems fired,
"autonomy_tick" with IAS, GAS, stage, and decisions,
plus bandit / curriculum / stage telemetry depending on the phase.
```

Everything is append-only, so replaying the ledger rebuilds the exact same tick decisions.
