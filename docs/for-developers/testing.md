# ✅ Testing PMM

PMM ships with a comprehensive pytest suite. Run it regularly when making changes.

## Quick smoke test

```bash
pytest -q
```

This exercises the core runtime in under a minute on most machines.

## Full test suite

```bash
pytest
```

The full run covers >150 modules, including autonomy, commitments, projections, and API helpers.

## Selecting subsets

- Specific file: `pytest tests/test_autonomy_loop.py`
- Keyword filter: `pytest -k "reflection and not slow"`
- Verbose mode: `pytest -vv`

## Useful environment flags

- `PYTEST_ADDOPTS="-n auto"` – parallelise tests (requires `pytest-xdist` if you install it)
- `PMM_MODEL=llama3` – pin a local model to avoid accidental OpenAI calls during CLI-based tests

## Regenerating snapshot data

Some tests rely on fixtures under `tests/data/`. If you change the event log schema, regenerate fixtures with the helper scripts in `scripts/` (e.g. `python scripts/verify_pmm.py`).

## Linting & type checks

Pair the test run with static checks for quicker feedback:

```bash
ruff check pmm tests
black --check pmm tests
mypy pmm
```

See [code-style.md](code-style.md) for details on the style tooling.
