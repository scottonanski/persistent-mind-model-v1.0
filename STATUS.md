# Persistent Mind Model v2 — Status

> Persistent Mind Model (PMM) is a deterministic, ledger-recall system. Every behavior, reflection, or summary must be reconstructable from the event ledger alone—no hidden state, no heuristics, no probabilistic shortcuts.

---

## Sprint Timeline (1-14

1. **Minimal v2 skeleton**  
   Core SQLite `event_log` with hash chain (timestamps excluded), `ledger_mirror`, `meme_graph` stub, schemas; minimal runtime loop (user → assistant → commitment → reflection) with `commitment_manager` and prompts; deterministic DummyAdapter (`COMMIT:` marker); baseline append/read integrity tests.

2. **Providers, validators, replay, initial CLI**  
   Deterministic adapters for OpenAI (temp=0, top_p=1) and Ollama, adapter factory; claim validators; read-only replay CLI; reproducible hash tests.

3. **Adaptive reflections & closures**  
   Structured markers only (`COMMIT`, `CLOSE`, `CLAIM`, `REFLECT`); delta-gated reflections; idempotent closures via `apply_closures`; tests for no-delta, commit/close, failed claim, reflect-block folding, idempotent close.

4. **Semantic extraction + replay narration**  
   Strict semantic extractor (line anchored JSON); deterministic replay narrator; runtime loop refactor to rely on structured parsing; extractor/narration tests.

5. **Ledger metrics & consistency checks**  
   Deterministic metrics computation (`event_count`, kind counts, broken links, last_hash, open vs closed commitments); idempotent `metrics_update`; CLI flags `--metrics` / `--append-metrics`; metrics regression tests.

6. **Primer + short-term context**  
   Canonical system primer prepended on each adapter call (“truth-first”, “No data in ledger.”); context builder with strict last-N user/assistant window; reflections remain delta-gated; primer/context/reflection tests.

7. **Deterministic diagnostics**  
   Per-turn `metrics_turn` (provider/model/tokens/lat_ms); DummyAdapter latency hints; CLI `/diag` to print last five diagnostics; coverage in diagnostics tests.

8. **Human-usable CLI**  
   Interactive model selector (Ollama JSON/table fallback, optional `openai:<model>`); chat loop commands `/replay`, `/metrics`, `/diag`, `/exit`; output hides `COMMIT` lines while preserving ledger entries; packaging via `pyproject.toml` (`pmm` console entry point); repo-local launcher retained.

9. **Reflection synthesis & identity summary**  
   `reflection_synthesizer.py` builds `{intent,outcome,next}` from latest user/assistant/metrics events; `identity_summary.py` appends `summary_update` every 3 reflections or >10 events (open commitments, reflections_since_last, last_event_id); runtime integration after `metrics_turn`; deterministic tests for both modules. Historical baseline tagged `v2.0-sprint8`.

10. **Full Autonomy Integration**  
   Autonomous supervisor launches at process boot, emits `autonomy_stimulus` every 10 seconds; listener parses event content for slot/slot_id, triggers `run_tick` which logs decision before executing reflections/summaries; debug prints gated by DEBUG flag; system runs silently, autonomously generating ticks without user intervention.

11. **Autonomous Commitment Review**  
   Differentiated autonomous reflections: commitment review synth. Fixes duplication; enables self-review.

12. **Stale Commitment Detection**  
   Autonomy kernel flags commitments as stale:1 if >20 events since oldest open commitment; deterministic threshold in kernel defaults.

13. **Auto-Close Stale Commitments**  
   Autonomous reflections auto-close commitments >30 events stale; appends commitment_close event with reason; re-calculates remaining open count and stale flag.

14. **Inter-Ledger References**  
   Echo can reference events from other PMM ledgers using `REF: <path>#<event_id>` syntax in any `assistant_message` or `reflection`. The referenced event is verified by hash, appended as `inter_ledger_ref`, and replay-safe. Includes parsing in runtime loop, REF proposal in autonomy reflection synthesizer, updated `/replay` narration with ✓/✗ status, and comprehensive tests.

15. **Cross-Mind Truth Alignment**  
   `claim_verification` events emitted on failed `inter_ledger_ref` verification. **Idempotent**: one event per unique `(path, event_id)` pair, reconstructed deterministically via `get_failed_ref_keys()`. Verified: `pytest -q` → **43/43 passed**. Live in `pmm_v2.db`: 2 `claim_verification`, 13 failed refs, **no duplicates**.

16. **Enhanced Self-Awareness in Reflections**  
   Reflections now include a `self_model` field when at least 5 user reflections exist, scanning for patterns and appending a deterministic string `'dynamic, process-defined identity'`. Enhances emergent self-awareness via ledger facts only, preserving replay determinism.

### Sprint 16: Emergent Self-Model — **COMPLETE** ✅
- `self_model` in reflections (≥5 user refs)
- `metrics_emergent` on high reflection/commitment load
- Fixed truth reminder in system prompt
- `identity_trend` in summaries (delta ≠0)
- All deterministic, ledger-safe
- Tests: **47/47**
- Tagged: `v2.0-sprint16`

### Sprint 17: Relational Memory Layer — **COMPLETE** ✅
- Mirror: O(1) open commitments, stale flags, reflection counts
- MemeGraph: deterministic causal graph (replies_to, commits_to, closes, reflects_on)
- Full rebuild from ledger → replay parity
- Listeners only — no Ledger mutation
- Tests: 8 new, all pass
- Tagged: `v2.0-sprint17`

## Sprint 18: Autonomy Telemetry

- Added `autonomy_metrics` event every 10 `autonomy_tick` via `AutonomyTracker`.
- Rebuildable from ledger, idempotent, listener-driven.
- Integrated into `/metrics` via `compute_metrics(tracker=...)`.
- Tests: rebuild parity, emit cadence, no-delta idempotency.
- Deterministic, replay-safe, no model calls.

### Sprint 19: Recursive Self-Model (RSM) — **COMPLETE** ✅
- Added `RecursiveSelfModel` in `ledger_mirror`: tendencies, gaps, meta-patterns
- Fully rebuildable from ledger, O(1) sync, replay-parity guaranteed
- RSM exposed in context, reflections, summaries
- Temporal diffing: `diff_rsm(id_a, id_b)` for self-evolution
- Autonomy monitors RSM via internal goal "monitor_rsm_evolution"
- `/rsm` CLI: query current/historical/diff
- Identity summary delta-gated on RSM changes
- All logic deterministic, ledger-native, no heuristics
- Tests: **31/31 passed**
- Tagged: `v2.0-sprint19`

### Sprint 20: Meta-Cognitive Commitment Layer — **COMPLETE** ✅
- `origin:"autonomy_kernel"` + `goal` in commitment events
- `open_internal()` / `close_internal()` with `mc_` cids
- Autonomy opens internal goals on RSM gaps >3
- Deterministic execution: analyze_knowledge_gaps
- `/goals` CLI + context exposure
- Metrics track `internal_goals_open` 
- All idempotent, replay-safe, ledger-native
- Tests: **14/14 passed**
- Tagged: `v2.0-sprint20`

### Measured Proof from `/replay`

| Event | Kind | Content | Verdict |
|------|------|--------|--------|
| [22] | `reflection` | `{commitments_reviewed:1,...}` | **Autonomous review** |
| [34] | `reflection` | `{commitments_reviewed:2,...}` | **Autonomous review** |
| [46] | `reflection` | `{commitments_reviewed:3,...}` | **Autonomous review** |
| [59] | `reflection` | `{commitments_reviewed:3,...}` | **Autonomous review (latest)** |

**No duplication of user intent.**  
**Autonomy triggers every ~10 events** (reflection_interval).  
**Commitments reviewed: 3** → matches `open_commitments: 3` in `/metrics`.

### Final State (v2 Revamp Success)

| Goal | Status |
|------|--------|
| Deterministic | Hashes stable, no randomness |
| Autonomous | Self-review without user input |
| Test-isolated | `autonomy=False` in tests |
| Replay-safe | `pmm --replay` will match exactly |
| **Better than v1** | No traits, no stages — pure ledger |

## Autonomy Kernel (Sprint 11)

### Rule Table

| Condition | Decision | Reasoning |
| --------- | -------- | --------- |
| No autonomous reflection recorded yet after the latest `metrics_turn` | reflect | Seed autonomy stream |
| Events since last autonomous reflection ≥ 10 | reflect | `reflection_interval` reached |
| Events since last summary ≥ 50 **and** ≥1 autonomous reflection since that summary | summarize | `summary_interval` reached |
| Otherwise | idle | No autonomous action needed |

Additional governance rules:
- Only reflections with `meta.source == "autonomy_kernel"` count toward `reflection_interval`. User-turn reflections do **not** reset the interval.
- Every tick decision—even `idle`—is logged before execution as an `autonomy_tick` with canonical JSON payload.
- Autonomous reflections append deterministic content via `reflection_synthesizer` and carry provenance `{"synth": "v2", "source": "autonomy_kernel"}`.
- `autonomy_rule_table` is persisted exactly once per ledger. Current hash: `ca68d073b140fce63170b9790db7acdef5b96487f8af533332a025fd54a1541f`.

Replay contract: identical ledgers reproduce the same sequence of `autonomy_tick`, reflection, and summary events byte-for-byte.

---

## Idempotency

- `claim_verification` events are emitted **once per unique failed reference target**.
- Duplicate `REF:` lines pointing to the same `(path, event_id)` pair do not generate redundant events.
- The set of failed references is reconstructed deterministically from existing `claim_verification` events in the ledger.

---

## Repository Layout

```
pmm_v2/
├─ adapters/                # Dummy, Ollama, OpenAI adapters + factory
├─ core/                    # event_log, ledger_mirror, meme_graph stub, schemas, validators, semantic_extractor, ledger_metrics
├─ runtime/                 # loop, autonomy_kernel, commitment_manager, reflection builder, reflection_synthesizer, identity_summary, prompts, context_builder, cli, replay_narrator
└─ tests/                   # loop, adapters, replay, determinism, validators, reflections, metrics, diagnostics, autonomy kernel, etc.
pyproject.toml              # packaging; exposes `pmm` console script
pmm                         # repo-local launcher
```

### Test Coverage (illustrative files)
- `tests/test_loop_basic.py`, `test_commit_open_triggers_reflection.py`, `test_close_only_triggers_reflection.py`, `test_failed_claim_triggers_reflection.py`
- `tests/test_no_delta_no_reflection.py`, `test_reflect_block_folds_in.py`, `test_reflection_events.py`
- `tests/test_metrics.py`, `test_diagnostics.py`, `test_determinism.py`
- `tests/test_replay_mode.py`, `test_replay_narration.py`
- `tests/test_autonomy_kernel.py`
- `tests/test_adapters_dummy_switch.py`, `test_semantic_extractor.py`, `test_idempotent_closure.py`, `test_validators.py`

---

## Determinism Guarantees

- Hash payloads include `kind`, `content`, `meta`, `prev_hash`; timestamps are excluded to allow replay parity.
- Runtime contains no randomness, wall-clock timing branches, or environment-conditioned behavior (beyond provider selection).
- Instrumentation events (`metrics_update`, etc.) are excluded from canonical metrics counts.
- Replay mode is read-only; narration never mutates the ledger.
- Reflections remain delta-gated and deterministically composed; adapters prepend the system primer and strict context window every turn.

---

## Runtime & CLI

```
source .venv/bin/activate
pytest -q

# CLI (installed or repo-local)
pmm        # select model once, then chat
# Commands: /replay  /metrics  /diag  /tick  /exit
```

- `/tick` prints the kernel decision and triggers autonomous reflections/summaries when non-idle.
- `/metrics` prints deterministic ledger metrics (`event_count`, open/closed commitments, hash, etc.).
- `/diag` lists the five most recent `metrics_turn` entries.

Expected baseline:
- All tests green (`pytest -q`)
- `/metrics` shows stable counts & hash
- `/replay` narrates latest 50 events
- `/diag` outputs last five diagnostics

---

## Recent Changes

- Sprint 11: Autonomous Commitment Review implemented and tested. Autonomous reflections now differentiate from user-turn reflections, reviewing open commitments without duplication. Test isolation via `autonomy=False` parameter added to RuntimeLoop.
- Full autonomy: supervisor launches at boot, emits stimuli every 10s, triggers ticks automatically; no manual `/tick` needed.
- Fixed `_on_autonomy_stimulus` to parse slot/slot_id from event content JSON.
- Fixed `run_tick` to log autonomy_tick before executing, avoiding recursion.
- Added DEBUG flag to gate debug prints; system runs silently by default.
- STATUS.md updated with full autonomy details for Sprint 10.
- Sprint 14: Inter-Ledger References implemented. Added `inter_ledger_ref` event kind with validation; parsing of `REF:` lines in assistant messages and reflections; optional REF proposal in autonomy reflections; updated `/replay` to show verification status; new tests for valid/invalid references.

---



