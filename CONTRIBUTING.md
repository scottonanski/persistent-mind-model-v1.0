# Contributing to Persistent Mind Model v2

> Persistent Mind Model (PMM) is a deterministic, ledger‑recall system. Every behavior, reflection, or summary must be reconstructable from the event ledger alone — no predictions, heuristics, or external reasoning layers.

PMM v2 prioritizes determinism, auditability, and autonomy. Every change must preserve byte‑stable behavior when replayed from the ledger. No speculation, no hidden state.

## 1. Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
ruff check
black --check .
```

Target: Python 3.10+
All tests must pass locally before opening a PR.

## 2. Core Rules

### Ledger Integrity

- Every event append must be reproducible from ledger + code alone.
- No duplicate policy_update when values are unchanged.
- Never emit events to “make tests pass.”

### Determinism

- No randomness, wall‑clock timing, or env‑based logic.
- Timestamps are excluded from digests and recorded only once at write‑time.
- Replays must produce identical hashes across machines.

### No Env Gates for Behavior

- Runtime behavior (budgets, cadence) must not depend on env vars.
- Env vars are allowed only for credentials or external API keys.

### No Regex / Keyword Heuristics

- Regex or brittle keyword matching is forbidden in runtime or ledger‑affecting code.
- Use structured parsing or semantic extractors only.
- Allowed in tests or tooling only.

### No Hidden User Gates

Autonomy **must** start at process boot and run continuously. It is **forbidden** to:

- Tie autonomy to CLI commands (/tick, /animate)
- Gate autonomy behind config flags
- Emit actions outside the ledger path

Any PR introducing a user-triggered autonomy path will be rejected.

### Idempotency

- If an operation yields no semantic delta, do not emit a new event.
- Re‑emission is allowed only on validated policy change.

## 3. Evolution / Reflection Policy

- reflection events are generated deterministically by reflection_synthesizer.py.
- summary_update events are periodic, every 3 reflections or > 10 events since last.
- Each reflection: {intent, outcome, next} — no hidden randomness, no model call.
- Summaries must contain only ledger facts (e.g., open commitments, reflection counts, last event id). No psychometric fields.
- Do not hand‑edit reflection or summary logic to “sound better.”

## 4. Testing Requirements

| Scope                  | Must Assert                                      | File Example                           |
| ---------------------- | ------------------------------------------------ | -------------------------------------- |
| Reflection Synthesizer | Deterministic identical output                   | tests/test_reflection_synthesizer.py   |
| Identity Summary       | Deterministic identical output; threshold logic  | tests/test_identity_summary.py         |
| Ledger Integrity       | No hash breaks                                   | tests/test_determinism.py              |
| CLI Runtime            | In‑chat commands `/replay /metrics /diag` stable | tests/test_diagnostics.py              |

All new modules must include direct tests. Tests must never stub or simulate unimplemented future behavior.

## 5. Commit & PR Discipline

- One logical change per commit.
- Use clear, imperative messages:
  - Fix: stabilize replay determinism in diagnostics path
  - Add: deterministic reflection synthesizer
- Reference issues or sprint IDs when relevant.
- Ensure CI passes (pytest + ruff + black).

## 6. Determinism Checklist (pre‑merge)

- [ ] No new randomness or external calls.
- [ ] No env‑dependent logic.
- [ ] All hashes reproduce across replays.
- [ ] Tests added and passing.
- [ ] Ledger schema untouched or versioned.
- [ ] STATUS.md and CHANGELOG.md updated if behavior visible to runtime.

## 7. Exceptions

- Regex/keywords may appear only in developer tools or tests.
- Experimental features must stay behind `--experimental` CLI flag and off by default.
- All runtime code must remain replay‑safe.

### Summary

PMM v2 = Determinism + Auditability + Autonomy. Any patch that breaks replay equivalence, hides logic in envs, or adds nondeterminism will be rejected.
