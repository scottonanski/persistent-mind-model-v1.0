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

## “Alive” Session Example

This repo injects a deterministic header (identity + open commitments) and prints clear breadcrumbs so short sessions feel purposeful without heuristic prompts.

Example (abridged):

```
$ python -m pmm.cli.chat
Hello!
You are Logos. Speak in first person.
Open commitments:
- Finish documenting the memory system
- Explore a new reflection strategy
Recent trait drift: +O -C

User: What are you working on?
Assistant: I’m tracking two commitments:
– Finish documenting the memory system
– Explore a new reflection strategy
[bridge] CurriculumUpdate→PolicyUpdate (src_id=123)
```

To verify end-to-end behavior, use the provided scripts:

```
chmod +x scripts/verify_pmm.sh scripts/verify_pmm.py
./scripts/verify_pmm.sh
```

This walkthrough asserts:
- identity_propose and identity_adopt events exist
- at least one trait_update and curriculum_update → policy_update bridge (by src_id)
- header lines appear in CLI output
- memory summary probe works: `python -m pmm.api.probe memory-summary`

## Phase‑5 Demo (meta_reflection + reward)

Run this one‑liner to seed a small, interleaved window of events that produces a non‑zero `meta_reflection` efficacy and a paired `bandit_reward`:

```bash
python - <<'PY'
from pathlib import Path
import json
from pmm.storage.eventlog import EventLog
from pmm.commitments.tracker import CommitmentTracker
from pmm.runtime.loop import _maybe_emit_meta_reflection

db = ".data/pmm.ci.db"; Path(".data").mkdir(exist_ok=True)
log = EventLog(db); ct = CommitmentTracker(log)

# Optional fast cadence seed (non‑bridge)
if not any(e["kind"]=="policy_update" and (e.get("meta") or {}).get("component")=="reflection" for e in log.read_all()):
    log.append(kind="policy_update", content="reflection cadence override",
               meta={"component":"reflection","params":{"min_turns":1,"min_time_s":0}})

# Interleave opens/closes within 5 reflections to yield efficacy > 0
log.append(kind="reflection", content="ci#1", meta={})
c1 = ct.add_commitment("Collect 3 trustworthy sources", project="research-inquiries")
log.append(kind="reflection", content="ci#2", meta={})
log.append(kind="reflection", content="ci#3", meta={})
c2 = ct.add_commitment("Draft 5-bullet explainer outline", project="research-inquiries")
log.append(kind="reflection", content="ci#4", meta={})
ct.close_with_evidence(c2, evidence_type="done", description="outline_draft_ready")
log.append(kind="reflection", content="ci#5", meta={})

_maybe_emit_meta_reflection(log, window=5)

evs = log.read_all()
mrs = [e for e in evs if e["kind"]=="meta_reflection"]
brs = [e for e in evs if e["kind"]=="bandit_reward" and (e.get("meta") or {}).get("source")=="meta_reflection"]
print(json.dumps({"meta_reflection": mrs[-1] if mrs else None,
                  "bandit_reward": brs[-1] if brs else None}, indent=2))
PY
```

You can also inspect the latest snapshot:

```bash
python -m pmm.api.probe snapshot --db .data/pmm.ci.db \
| jq '{kinds: [.events[].kind] | group_by(.) | map({k:.[0], n:length})}'
```

### Projects (group commitments)

You can optionally group commitments under a project by tagging opens:

```python
from pmm.commitments.tracker import CommitmentTracker
from pmm.storage.eventlog import EventLog

ct = CommitmentTracker(EventLog(".data/pmm.db"))
cid = ct.add_commitment("Write probe docs.", project="docs")
```

PMM emits `project_open` once per `project_id` and auto-emits `project_close` when the last child commitment under that project closes. The CLI header shows the top project as:

```
[PROJECT] docs — 1 open
```
