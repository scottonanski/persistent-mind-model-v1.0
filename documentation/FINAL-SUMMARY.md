# Final Summary (Commitments, Traits, and Emergence)

## What We Discovered
- No commitment bug: lifecycle is correct and complete.
- Session analysis: 100% lifecycle completion; 0 orphans.
- Extraction working: conservative; e.g., 11 accepted out of 188 candidates (~5.8%).
- Traits accurate: C=0.00 reflects low commitment density.

## What Looked Wrong vs What’s True
- “Commitments vanish” → They close/expire normally.
- “C trait stuck at 0.00” → Accurate for short, low-density commitments.
- “Validators are too strict” → They correctly prevent fabrications.
- “Open count fluctuates” → Normal lifecycle behavior.

## Key Insights
1) Conservative extraction is intentional (filters conversational phrases).
2) Stage progression ≠ commitment density; S4 achievable with C low.
3) The model reflects reality: philosophical depth can drive IAS/GAS even if C stays low.

## What’s Next (No Fix Needed)
- Optional: configurable thresholds; semantic detection improvements; extraction-rate monitoring.
- Improve observability, not behavior: show extraction rates, lifecycle stats, and expected ranges.

## Honest Assessment
- Architecture: solid (event-sourced identity, deterministic projections).
- Implementation: correct (lifecycle tests, invariant enforcement).
- Gap: external observability (metrics were misleading without lifecycle context).

## Research Framing
- Treat PMM as an experimental apparatus: you infer behavior from ledger traces.
- Emergent behavior is expected; the goal is measurement and reproducibility.

See also:
- `documentation/OBSERVABILITY.md` for health indicators and queries
- `documentation/INVARIANTS.md` for event ↔ check mapping
- `documentation/EVENTS.md` for canonical event examples

