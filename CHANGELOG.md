## v2.0-sprint19 — Recursive Self-Model (RSM)

- Added `RecursiveSelfModel` within `ledger_mirror` tracking tendencies, gaps, meta-patterns
- Ensured rebuildable, O(1) sync pipeline with replay parity
- Surfaced RSM data in context builder, reflections, and identity summaries
- Introduced `diff_rsm(id_a, id_b)` for temporal self-evolution analysis
- Wired autonomy internal goal `monitor_rsm_evolution` to watch RSM drift
- Extended `/rsm` CLI command for current, historical, and diff queries
- Delta-gated identity summaries on significant RSM changes
- Deterministic, ledger-native implementation with full test coverage (31/31)

## v2.0-sprint21 — RSM Stability & Adaptability

- Added `stability_emphasis` and `adaptability_emphasis` trackers to RSM
- Counts case-insensitive substring occurrences in assistant/reflection content
- Capped each counter at 50 to bound runtime without affecting determinism
- Snapshots consumed by identity summaries; deltas surface automatically
- Tests cover counting (45 from 15 events × 3) and cap at 50; replay parity preserved

- Added `instantiation_capacity` tracker (markers: `instantiation`, `entity`), capped at 50; identity summaries append "+N instantiation" when increasing.
- Added `uniqueness_emphasis` derived from unique event hash prefixes: `int((unique/total)*10)` capped at 20; identity summaries append "+N uniqueness". Deterministic and O(n) over the ledger; minor context display guard to avoid bloating output when uniqueness is the only signal.
 - Autonomy idle optimization: auto-closes stale commitments when more than 2 open and stale by `commitment_auto_close` threshold; closes in open order with reason `auto_close_idle_opt`. Tests added.
