# Contributing to Persistent Mind Model (PMM)

Thank you for contributing to PMM. This project prioritizes auditability, determinism, and autonomy. Please keep changes small, well-tested, and aligned with the principles below.

## Development setup

- Python 3.10+
- Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- Run tests and linters locally before opening a PR:

```bash
pytest -q
ruff check
black --check .
```

## Guardrails (Kernel Principles)

- __Ledger integrity__
  - Event emissions must be idempotent and reproducible from the log alone.
  - Avoid duplicate `policy_update` or `stage_update` events when nothing has changed.
  - Do not add events just to satisfy tests.

- __Evolution events__
  - Only emit `evolution` when `meta.changes` is non-empty.
  - Clamp all tunables deterministically (e.g., `min(0.9, current + 0.05)`).

- __Stage stability__
  - Stage transitions must respect hysteresis and avoid thrashing near boundaries.
  - No hidden/implicit stage overrides that bypass `StageTracker`.

- __Determinism__
  - No runtime clock/RNG/external-state dependencies in decision logic (beyond timestamps recorded in the ledger by append-only writes).

- __No test overfitting__
  - Fix root causes. If a test is brittle, propose a test change rather than warping runtime logic.

## Important Idempotency Nuance (Reflection Policy)

- __policy_update(component="reflection")__
  - Emit exactly once per stage change, even if the parameters match historical values for that stage.
  - Do not re-emit while the stage remains unchanged and the parameters are identical.
  - Rationale: This preserves a clear, stage-driven policy timeline without spamming identical updates across ticks.

## Pull requests

- Keep PRs focused and small when possible.
- Include tests for new behavior and bug fixes.
- Update documentation when behavior or APIs change.
- Ensure CI passes (tests, lint, formatting).
- Use clear, imperative commit messages and reference issues where relevant (e.g., "Fix: stabilize stage transitions near S1/S2 boundary").

---
Questions? Open an issue or start a discussion. Thank you for helping improve PMM.
