# Fresh start

## Observability: Read-only Probe

Use the Probe API to inspect PMM state directly from the SQLite event log. It performs no writes and makes no network calls.

- Guide: [docs/guide/probe.md](docs/guide/probe.md)
- One-liner CLI example (pretty-printed JSON):

```bash
python -m pmm.api.probe --db .data/pmm.db --limit 20
```

For programmatic use, see `snapshot(...)` for the last ≤ N events and `snapshot_paged(...)` for forward pagination with `next_after_id`. Optional redaction lets you trim large `content` or strip blobs at the API layer (storage remains unchanged).

## Clean-Slate Alpha (v0.2.0)

This milestone represents the first stable baseline of the clean-slate branch.
It captures the essential persistence, commitments, and reflection mechanisms
with CI fully green.

Current features:
- **Append-only EventLog (SQLite + hash chain):** every event stored immutably with integrity checks.
- **Projection of identity and commitments:** derive current state from the event log without mutation.
- **Commitment tracking:** pluggable detectors (regex baseline, semantic stub) extract “I will …” plans; evidence from “Done: …” closes them.
- **End-to-end closure test:** full workflow validated from commitment open through closure in projection.
- **ReflectionCooldownManager:** gates self-reflection by turns, time, and novelty to avoid loops.
- **IAS/GAS telemetry:** simple metrics of alignment and growth, embedded in reflection events.
- **CI green on GitHub Actions:** full test suite passing upstream for reproducibility.

## Guides

- **API (read-only):** see [`docs/guide/api_server.md`](docs/guide/api_server.md)
- **Bandit bias (schema-driven):** see [`docs/guide/bandit_bias.md`](docs/guide/bandit_bias.md)
- **Embeddings backlog (CLI):** see [`docs/guide/embeddings_backlog.md`](docs/guide/embeddings_backlog.md)

### Pre-commit hooks (optional)

Install and enable hooks locally to keep formatting and linting consistent:

```bash
pip install pre-commit
pre-commit install
```

This repo ships with `.pre-commit-config.yaml` to run `ruff --fix` and `black` on staged files.
