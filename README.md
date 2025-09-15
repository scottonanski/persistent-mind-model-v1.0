# Persistent Mind Model (PMM)

PMM is a small runtime that turns a language model into a steady, self-improving “mind”.

It is not just a chat wrapper.

PMM is **ledger-first**: every thought, decision, and change is written to an append-only, hash-chained event log. That makes behavior auditable, reproducible, and resistant to hidden prompt state or “drift”.

### *Okay, great... But what does this even mean? It sounds like a bunch of nerd-speak!*

You're right, it does. Here’s the plain version:

* **What it does right now:** PMM runs a loop around a language model, logs every action to a tamper-resistant event chain, and reuses that log to maintain a consistent state across turns.
* **What it’s designed for:** building a persistent “mind” that remembers, self-assesses, and steadily improves instead of resetting each session.
* **What’s still in progress:** some of the “mind-like” behaviors (like autonomous self-assessment and self-improvement) are still being tested and tuned.

Because of this, PMM can watch its own behavior and change itself over time, instead of just reacting in the moment.

### Breaking down the jargon

* **Append-only** means nothing gets erased or rewritten. Every step is added in order.
* **Hash-chained** means each step is mathematically linked to the one before it, so tampering shows up immediately.
* Together, this makes PMM’s behavior **traceable and verifiable** instead of being hidden inside a black-box prompt.
* **Resistant to drift** means it doesn’t silently lose track of who it is or what it’s doing. Its state is anchored to the log, not to temporary chat history.


## In One Line

Self‑evolving AI mind kernel — where identity, memory, and growth are first‑class, provable system properties.

## What It Does (Plain Terms)

- Maintains identity: proposes and adopts a name; keeps a consistent voice and trait profile across turns.
- Evolves autonomously: runs a background loop that reflects, self‑assesses, and adjusts its own reflection cadence (within safe bounds).
- Tracks work: opens, assigns, and closes “commitments” (tasks), grouping related ones into projects automatically.
- Verifies itself: ships a script that checks invariants (e.g., 1:1 policy linkage, correct self‑assessment windows, project rules).
- Shows its reasoning: prints a header with identity, the top open commitments, and why it did or didn’t reflect this turn.

## How It Works

- Append‑only event log (SQLite): all events are time‑stamped and hash‑chained for integrity.
- Autonomy loop: every few seconds, PMM looks at recent events (ledger), computes simple “health” metrics, and decides whether to reflect.
- Reflection → commitments: reflections produce tiny next‑steps; PMM may open a matching commitment and later close it when it sees evidence.
- Meta‑reflection (every 5 reflections): summarizes “opened vs. closed” and effectiveness for that window.
- Self‑assessment (every 10 reflections): richer stats (e.g., average close lag, hit rate) plus a fingerprint of the exact window; may trigger a small cadence policy tweak, safely clamped and with deadband to avoid flapping.

## Quick Start

### 0) Install (Linux, macOS, Windows)

- Prereqs: Git, Python 3.10+ (3.11 recommended), pip. For verify: `jq` (CLI JSON tool).

- Linux (Ubuntu/Debian):
  - `sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip jq`
  - `git clone https://github.com/USERNAME/persistent-mind-model.git && cd persistent-mind-model`
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -U pip && pip install -e .`  # add `.[dev]` for dev tools/tests

- macOS:
  - Install Homebrew if needed, then: `brew install python jq`
  - `git clone https://github.com/USERNAME/persistent-mind-model.git && cd persistent-mind-model`
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -U pip && pip install -e .`

- Windows (PowerShell):
  - Install Python 3.10+ from python.org and Git for Windows.
  - Optional: `choco install jq` (or use Git Bash and `jq` via `pacman` in MSYS2).
  - `git clone https://github.com/USERNAME/persistent-mind-model.git` then `cd persistent-mind-model`
  - `py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1`
  - `python -m pip install -U pip && pip install -e .`

Configure your `.env` (copy then edit):

```
cp .env .env.local || true
```

Open `.env` (or `.env.local`) and set at least:

```
OPENAI_API_KEY=sk-...      # required for the default OpenAI chat adapter
# Optional knobs
# OPENAI_MODEL=gpt-4o-mini  # or PMM_MODEL to override
# PMM_AUTONOMY_INTERVAL=10  # seconds between background ticks (0 disables)
# PMM_COLOR=0               # disable colored notices in CLI
```

### 1) Start a chat (metrics view on):

```bash
python -m pmm.cli.chat --@metrics on
```

### 2) Verify what happened (scoped, deterministic checks):

```bash
bash scripts/verify_pmm.sh .logs_run .data/pmm.db
```

### 3) Inspect the event log directly:

```bash
python -m pmm.api.probe snapshot --db .data/pmm.db --limit 50 | jq .
```

## Beginner Quickstart (3 minutes)

Think of PMM like a tidy “mind notebook.” It writes down everything it thinks or decides. You can start small:

1) Create the notebook and start talking
- Run: `python -m pmm.cli.chat --@metrics on`
- You’ll see a header line (identity, open items) and a reason why it reflected or not.

2) Ask simple things
- “What are you working on?” → it mentions top open items from its notebook.
- “Reflect on your last answer.” → it writes a short reflection (and may open a tiny task).

3) Check the notebook
- `python -m pmm.api.probe snapshot --db .data/pmm.db --limit 30 | jq .`
- You’ll see entries like `reflection`, `commitment_open`, `policy_update` — everything is written down.

That’s it. PMM is just a careful mind that writes everything to a ledger.

## Concepts in Everyday Terms

- Ledger (event log) = a diary. PMM never edits past pages; it only adds new entries.
- Identity = a name and voice it sticks to, so it sounds like the same person every time.
- Reflection = short journaling: “what changed, what I’ll adjust next.”
- Commitments = to‑dos the mind opens and later checks off when evidence arrives.
- Projects = folders that group related to‑dos.
- Policy = a rule like “how often should I reflect?”
- Self‑assessment = a periodic review: “how did the last stretch go?” It may slightly tweak a policy.

## Common Tasks (Copy/Paste)

- Start the read‑only API (local):
  - `python -m uvicorn pmm.api.server:app --host 127.0.0.1 --port 8000 --reload`
  - Browse docs: http://127.0.0.1:8000/docs

- Verify a run (writes logs to `.logs_run/`):
  - `bash scripts/verify_pmm.sh .logs_run .data/pmm.db`

- Show a memory summary:
  - `python -m pmm.api.probe memory-summary --db .data/pmm.db | jq .`

- Demo self‑assessment output:
  - `scripts/demo_self_assessment.sh .data/pmm.db`

- Turn off the background loop (no autonomy):
  - `export PMM_AUTONOMY_INTERVAL=0` (Windows PowerShell: `$env:PMM_AUTONOMY_INTERVAL=0`)

- Disable colored notices (for clean logs):
  - `export PMM_COLOR=0` (Windows PowerShell: `$env:PMM_COLOR=0`)

## Troubleshooting

- “OPENAI_API_KEY not set”
  - Add your key to `.env` (or your shell env): `OPENAI_API_KEY=sk-...`
  - Restart your shell or re‑activate the venv.

- `uvicorn: command not found`
  - Install dev extras: `pip install -e .[dev]` (or `pip install uvicorn`).

- `jq: command not found`
  - Linux: `sudo apt-get install jq`
  - macOS: `brew install jq`
  - Windows: use `choco install jq` or run probes without jq.

- Windows PowerShell can’t run activation script
  - Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` in an admin shell once.

- Nothing shows in `.data/`
  - PMM writes events on demand; start a chat or run a verify script to generate entries.

## FAQ (Short)

- Is this just prompt engineering?
  - No. PMM’s behavior is driven by the ledger and explicit policies. Every change is recorded and can be verified later.

- Can I use a provider other than OpenAI?
  - Yes. The code includes other adapters (e.g., Ollama). Switch provider/model via env (see `pmm/llm/factory.py`).

- Is the API safe to run locally?
  - Yes. It’s read‑only: it never writes to your ledger; it only reads from the SQLite database you point it at.

## Key Ideas (Glossary)

- Event log: append‑only source of truth; events like `user`, `response`, `reflection`, `commitment_open/close`, `policy_update`.
- Identity: a proposed/adopted name and traits; used to keep voice steady and behavior consistent.
- Reflection: short, structured self‑notes (“what changed; what to adjust next”).
- Commitments & projects: tasks the agent opens/closes; related tasks cluster into projects with `project_open/assign/close` events.
- Cadence & policies: explicit rules for how often to reflect; self‑assessment can adjust them slightly (within bounds).
- Verification: a script that replays the ledger to assert invariants and catch regressions.

## Where Things Live

- Runtime loop and autonomy: `pmm/runtime/loop.py`
- CLI chat: `pmm/cli/chat.py`
- Verify script: `scripts/verify_pmm.sh`
- Metrics header: `pmm/runtime/metrics_view.py`
- Commitments/projects: `pmm/commitments/tracker.py`
- Cadence rules: `pmm/runtime/cadence.py`
- Event log (SQLite + hash chain): `pmm/storage/eventlog.py`

---

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

---

## Phase‑6 (Self‑Assessment & Policy Tuning)

PMM emits a `self_assessment` every 10 reflections with:

- Window metadata: `window=10`, `window_start_id`, `window_end_id`, and `inputs_hash` (sha256 of the 10 reflection ids) for idempotency and replay.
- Metrics: `opened`, `closed`, `actions`, `trait_delta_abs`, `efficacy`, `avg_close_lag`, `hit_rate`, `drift_util`.
- Actions are counted deterministically from reflection‑sourced commitment openings.

After each self‑assessment, PMM may emit a small `policy_update` for the reflection cadence with:

- Source tag: `meta.source="self_assessment"` (keeps bridge checks clean).
- Deadband: ignores tiny deltas to avoid flapping.
- Clamps: keeps cadence within safe bounds (turns: 1–6; seconds: 10–300).
- Snapshots: includes `prev_policy` and `new_policy` for audit.

Every 3 self‑assessments, PMM emits an `assessment_policy_update` with a round‑robin formula `v1 → v2 → v3` and a `rotation_index` for determinism.

You can see the latest SA and policy tweaks with:

```bash
scripts/demo_self_assessment.sh .data/pmm.db
```
