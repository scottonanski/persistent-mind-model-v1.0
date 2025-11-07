# Persistent Mind Model — Status

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
   `claim_verification` events emitted on failed `inter_ledger_ref` verification. **Idempotent**: one event per unique `(path, event_id)` pair, reconstructed deterministically via `get_failed_ref_keys()`. Verified: `pytest -q` → **43/43 passed**. Live in `.data/pmmdb/pmm.db`: 2 `claim_verification`, 13 failed refs, **no duplicates**.

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

### Sprint 21: RSM Stability & Adaptability — COMPLETE ✅
- Enriched `RecursiveSelfModel` with two new tendencies: `stability_emphasis`, `adaptability_emphasis`.
- Deterministic counting of substring occurrences across `assistant_message` and `reflection` kinds.
- Runtime cap at 50 per tendency to bound processing while preserving replay equivalence.
- Identity summaries auto-detect positive deltas via existing `_compute_rsm_trend` path (no policy change).
- Tests added to validate counts (45 from 15 events × 3 hits) and cap at 50; rebuild parity guaranteed.

- Added `instantiation_capacity` tendency: counts `instantiation` and `entity` mentions across assistant/reflection content, capped at 50. Identity summary trend description includes "+N instantiation" on positive deltas.

- Added `uniqueness_emphasis` tendency: computes an integer score from unique event hash prefixes: `int((unique_prefixes / max(1,total_events)) * 10)`, capped at 20. Deterministic via ledger `hash` fields; identity summaries include "+N uniqueness" when increased. Context hides RSM block if uniqueness is the only non-zero tendency (keeps chat context compact).

- Autonomy idle optimization: auto-closes stale commitments when there are more than 2 open and each is stale by event-count threshold (`commitment_auto_close`, default 27). Deterministic by processing opens in event order; emits `commitment_close` with `reason:"auto_close_idle_opt"`. Tests cover close vs. no-close threshold behavior.

- Added replay performance metric `replay_speed_ms` (ms/event) measuring `read_all()+hash_sequence()` via a monotonic timer; tracked in metrics for O(n) replay monitoring with test coverage.