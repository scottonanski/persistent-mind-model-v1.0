# Persistent Mind Model — Status

> Persistent Mind Model (PMM) is a deterministic, ledger-recall system. Every behavior, reflection, or summary must be reconstructable from the event ledger alone—no hidden state, no heuristics, no probabilistic shortcuts.

---

## Sprint Overview

### Sprint 1 — Minimal v2 Skeleton
- Core SQLite `event_log` with hash chain (timestamps excluded)
- `ledger_mirror`, `meme_graph` stub, schemas
- Minimal runtime loop (user → assistant → commitment → reflection) with `commitment_manager`
- Deterministic `DummyAdapter` using `COMMIT:` marker
- Baseline append/read integrity tests

### Sprint 2 — Providers, Validators, Replay, CLI
- Deterministic adapters for OpenAI (temp=0, top_p=1) and Ollama
- Claim validators and adapter factory
- Read-only replay CLI, reproducible hash tests

### Sprint 3 — Adaptive Reflections & Closures
- Structured markers: `COMMIT`, `CLOSE`, `CLAIM`, `REFLECT`
- Delta-gated reflections and idempotent `apply_closures`
- Tests: no-delta, commit/close, failed claim, reflect-block folding, idempotent close

### Sprint 4 — Semantic Extraction & Replay Narration
- Strict semantic extractor (line-anchored JSON)
- Deterministic replay narrator and runtime refactor for structured parsing
- Extractor and narration test coverage

### Sprint 5 — Ledger Metrics & Consistency Checks
- Deterministic metrics computation (event counts, kinds, broken links, etc.)
- Idempotent `metrics_update` and CLI flags `--metrics` / `--append-metrics`
- Metrics regression tests

### Sprint 6 — Primer & Short-Term Context
- Canonical system primer prepended on each adapter call (“truth-first”, “No data in ledger.”)
- Context builder with strict last-N window; reflections remain delta-gated
- Primer/context/reflection tests

### Sprint 7 — Deterministic Diagnostics
- Per-turn `metrics_turn` covering provider/model/tokens/latency
- DummyAdapter latency hints and CLI `/diag`
- Diagnostics test coverage

### Sprint 8 — Human-Usable CLI
- Interactive model selector (Ollama JSON/table fallback, optional `openai:<model>`)
- Chat commands `/replay`, `/metrics`, `/diag`, `/exit`
- Output hides `COMMIT` lines while preserving ledger entries
- Packaging via `pyproject.toml` (`pmm` console entry-point)

### Sprint 9 — Reflection Synthesis & Identity Summary
- `reflection_synthesizer.py` builds `{intent,outcome,next}`
- `identity_summary.py` appends `summary_update` every 3 reflections or >10 events
- Runtime integration after `metrics_turn`
- Tests ensure determinism; baseline tagged `v2.0-sprint8`

### Sprint 10 — Full Autonomy Integration
- Autonomy supervisor emits `autonomy_stimulus` on a 10s cadence
- Listener triggers `run_tick`, logging decisions before execution
- Debug prints gated by `DEBUG`
- System can run unattended, generating ticks without user input

### Sprint 11 — Autonomous Commitment Review
- Differentiated autonomous reflections for commitment review
- Eliminates duplication and enables self-review

### Sprint 12 — Stale Commitment Detection
- Autonomy kernel flags commitments as stale when >20 events elapsed since oldest open
- Deterministic default threshold inside kernel

### Sprint 13 — Automatic Closure of Stale Commitments
- Autonomy closes commitments >30 events stale
- Emits `commitment_close` with reason, recomputes stale flags

### Sprint 14 — Inter-Ledger References
- Support `REF: <path>#<event_id>` references across ledgers
- Verifies referenced event by hash and logs `inter_ledger_ref`
- Runtime parsing, autonomy reflection proposals, `/replay` enhancements, full tests

### Sprint 15 — Cross-Mind Truth Alignment
- `claim_verification` events on failed `inter_ledger_ref` verification (idempotent per key)
- Verified by `pytest -q` (43/43 passed); production ledger shows expected unique entries

### Sprint 16 — Emergent Self-Model ✅
- Adds `self_model` in reflections after ≥5 user reflections
- Introduces `metrics_emergent` and `identity_trend` deltas
- Tests: 47/47; tagged `v2.0-sprint16`

### Sprint 17 — Relational Memory Layer ✅
- Mirror exposes O(1) commitment state, stale flags, reflection counts
- MemeGraph builds deterministic causal graph
- Listener-only, rebuildable from ledger with parity tests
- Tagged `v2.0-sprint17`

### Sprint 18 — Autonomy Telemetry
- `autonomy_metrics` events every 10 ticks via `AutonomyTracker`
- Ledger-rebuildable, idempotent listener
- `/metrics` integration with tracker path
- Deterministic tests for cadence and no-delta behavior

### Sprint 19 — Recursive Self-Model ✅
- `RecursiveSelfModel` tendencies, gaps, meta-patterns
- `/rsm` CLI for current, historical, and diff views
- Identity summary updates gated on RSM changes
- Tests: 31/31; tagged `v2.0-sprint19`

### Sprint 20 — Meta-Cognitive Commitment Layer ✅
- Commitment events capture `origin:"autonomy_kernel"` and `goal`
- Internal goals via `open_internal()` / `close_internal()` using `mc_` CIDs
- `/goals` CLI and metrics integration
- Tests: 14/14; tagged `v2.0-sprint20`

### Sprint 21 — RSM Stability & Adaptability ✅
- Adds `stability_emphasis` and `adaptability_emphasis` tendencies (capped at 50)
- Extends tendencies with `instantiation_capacity` and `uniqueness_emphasis`
- Autonomy idle optimization auto-closes when >2 commitments and past threshold (reason `auto_close_idle_opt`)
- Adds `replay_speed_ms` performance metric

### Sprint 22 — Structured Execution Bindings ✅
- Structured `{ "type":"exec_bind", "cid":"…", "exec":"idle_monitor" }` config events
- `IdleMonitor` emits `metric_check` per tick, escalates to internal goal `explore_rsm_drift`
- `ExecBindRouter` activates executors without heuristics; CLI `/bindings`
- Regression test `test_exec_binding_idle_monitor.py`
