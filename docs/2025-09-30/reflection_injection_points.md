# Reflection Injection Points (Clean‑Slate PMM)

This document lists the precise pre-append injection points for reflection acceptance gates, along with pre/post-conditions and ordering guarantees that preserve existing tests.

## Primary Injection — `Runtime.reflect()`

- **Location**: `pmm/runtime/loop.py:Runtime.reflect()` before the first `eventlog.append(kind="reflection", ...)`.
- **Pre‑conditions**:
  - LLM has returned candidate reflection text (`note`).
  - No `reflection` has been appended yet in this invocation.
- **Automatic acceptance policy**:
  - Authoritative by default: if `accept(note, events, stage, opts)` returns `accepted=False`, append a single `debug` with `meta` including `{"reflection_reject": reason, "scores": meta, "accept_mode": "authoritative"}` and skip the reflection path this tick (no `reflection_check`, `commitment_open`, `insight_ready`, `bandit_arm_chosen`).
  - Forced recovery fallback: in early stages S0/S1 when consecutive stuck skips are detected (≥4 with reasons in `{min_turns, min_time, low_novelty}`), switch to audit‑only for this invocation. Proceed with the reflection path and defer a `debug` after `reflection_check`/`commitment_open` with `accept_mode: "audit"` if the gate would have rejected.
- **Post‑conditions (ordering preserved)**:
  - On acceptance (or audit‑only fallback): `reflection` → `reflection_check` → `[commitment_open?]`.

## Secondary Injection — `emit_reflection()`

- **Location**: `pmm/runtime/loop.py:emit_reflection()` before internal `eventlog.append(kind="reflection", ...)`.
- **Behavior**:
  - Always audit‑only in this helper (never suppress). If the gate would reject, append a `debug` with `accept_mode: "audit"`, then proceed with the reflection path unchanged.
- **Post‑conditions (ordering preserved)**:
  - `reflection` → `reflection_check` → `[commitment_open?]`.

## Non‑Injection Sites (leave as‑is)

- `_append_reflection_check()` — must remain immediately after an accepted `reflection` append.
- `maybe_reflect()` — remains responsible only for cooldown/due; do not insert gating here.
- `AutonomyLoop.tick()` — emits `insight_ready` (when applicable) and a single canonical `bandit_arm_chosen`, and ends with `autonomy_tick`.

## Ordering Guarantees (from tests)

- `reflection` is immediately followed by `reflection_check` for that reflection.
- Any `commitment_open` tied to a reflection follows that reflection's `reflection_check`.
- `bandit_arm_chosen` occurs after the reflection path for that tick.
- `autonomy_tick` ends the tick.
- If embeddings are enabled, the `embedding_indexed|embedding_skipped` event for a reflection lands immediately after the `reflection` content append and before `reflection_check`.

## Acceptance API (for reference)

- Module: `pmm/runtime/reflector.py`
- Signature: `accept(text: str, events: list[dict], stage: str | None, opts: dict | None = None) -> tuple[bool, str, dict]`
- Gate set: text hygiene → n‑gram dedup → optional embedding duplicate → one‑shot bootstrap accept (only bypasses dedup/embedding; hygiene must pass).
