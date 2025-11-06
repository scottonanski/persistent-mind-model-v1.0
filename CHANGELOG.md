## v2.0-sprint19 — Recursive Self-Model (RSM)

- Added `RecursiveSelfModel` within `ledger_mirror` tracking tendencies, gaps, meta-patterns
- Ensured rebuildable, O(1) sync pipeline with replay parity
- Surfaced RSM data in context builder, reflections, and identity summaries
- Introduced `diff_rsm(id_a, id_b)` for temporal self-evolution analysis
- Wired autonomy internal goal `monitor_rsm_evolution` to watch RSM drift
- Extended `/rsm` CLI command for current, historical, and diff queries
- Delta-gated identity summaries on significant RSM changes
- Deterministic, ledger-native implementation with full test coverage (31/31)
