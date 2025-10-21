# Persistent Mind Model (PMM)

Persistent Mind Model is a deterministic, event-sourced runtime that gives large language models persistent memory, autonomous reflection, and auditable behaviour. The system replays a hash-chained ledger to rebuild identity, commitments, and metrics so behaviour stays stable regardless of which model provider generates the text.

---

## What PMM Provides

- **Ledger-defined identity** – every interaction becomes an append-only event with SHA-256 chaining for tamper detection (`pmm/storage/eventlog.py:44`). The ledger is the mind; replay it and you deterministically rebuild identity, commitments, and traits.
- **Model-agnostic orchestration** – the runtime builds the same prompt context for any adapter via `LLMFactory` (`pmm/llm/factory.py:32`). Adapters for OpenAI, Ollama-hosted models, and a dummy test harness ship today; adding Claude, Grok, Gemini, or others is just a new `ChatAdapter`.
- **Autonomous evolution loop** – a background scheduler recomputes IAS/GAS, runs reflections, re-evaluates identity, and maintains commitments without user nudges (`pmm/runtime/loop.py:2088`).
- **Deterministic reflection + commitment pipeline** – reflections follow templated prompts, log rewards, and drive commitment extraction and restructuring (`pmm/runtime/loop/reflection.py:1`, `pmm/commitments/extractor.py:1`).
- **Real-time observability** – the Companion API and Next.js UI expose ledger state, metrics, traces, and commitments for inspection (`pmm/api/companion.py:95`, `ui/src/components/chat/detailed-metrics-panel.tsx:1`).

---

## Runtime at a Glance

```
User / Autonomy Tick
        │
        ▼
context_builder → build_context_from_ledger  (ledger slice + projections)
        │
        ▼
LLM adapter (OpenAI / Ollama / custom)
        │
        ▼
eventlog.append()  →  hash-chained ledger + embeddings (optional)
        │
        ├──► AutonomyLoop (reflections, commitments, stage, metrics)
        └──► Projections (LedgerSnapshot, MemeGraph, Metrics, TraceBuffer)
                │
                ▼
Companion API  →  UI / integrations / analytics
```

---

## Why “The Ledger Is the Mind”

- **Identity lives in the ledger** – traits, commitments, reflections, policy updates, and telemetry are all events. Swap the model and replay the ledger; the same identity re-emerges because nothing depends on provider-specific weights.
- **Adapters are lenses** – `ChatAdapter` implementations for OpenAI and Ollama already ship, and the interface stays small so Claude, Grok, Gemini, or any future provider can drop in without touching the runtime core.
- **Deterministic evolution** – IAS (identity stability) and GAS (commitment-driven growth) are recomputed from the ledger, making behaviour reproducible and auditable.
- **Cohesive narrative** – the runtime’s reflections, commitments, and stage transitions are simply ledger interpretations; the LLM supplies language, the ledger supplies identity.

> “The ledger **is** the mind. The LLM is just the current expression of it.” — excerpt from an early Claude walkthrough

---

## Core Concepts

- **Event Log** – `EventLog` maintains the append-only SQLite ledger with SHA-256 hash chaining. Hash verification is opt-in via `verify_chain()` and used by invariant checks (`pmm/storage/eventlog.py:421`, `pmm/runtime/invariants_rt.py:44`). Copy `.data/pmm.db` to migrate or back up state.
- **Context Builder** – `build_context_from_ledger` assembles deterministic system prompts using tail slices, with fallbacks to full snapshots when data is missing (`pmm/runtime/context_builder.py:1`).
- **Reflections & Bandit** – forced and autonomous reflections share templated instructions, log telemetry, and use a context-aware epsilon-greedy bandit for style selection. Stage context is stored in rewards; full stage-aware exploitation is partially wired (`pmm/runtime/loop/reflection.py:589`, `pmm/runtime/reflection_bandit.py:56`).
- **Commitment Lifecycle** – commitments are detected semantically, restructured, tracked, and prioritised so the runtime can open, close, or expire them deterministically (`pmm/commitments/extractor.py:1`, `pmm/commitments/tracker.py:1`).
- **Metrics & Evolution** – IAS/GAS are recomputed when relevant events occur, decay over time, and feed stage progression and introspection reports (`pmm/runtime/metrics.py:1`, `pmm/runtime/stage_tracker.py:1`).

---

## Getting Started

### Runtime Only

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
pip install -e .[dev]  # optional tooling
```

Create `.env`:

```bash
OPENAI_API_KEY=sk-...
PMM_PROVIDER=openai    # openai, ollama, or dummy
PMM_MODEL=gpt-4o-mini  # or llama3 / mistral / ...
PMM_DB=.data/pmm.db    # optional override
```

Launch the CLI:

```bash
python -m pmm.cli.chat
```

Use `--@metrics on`, `--@reflect`, or `--@models` to exercise runtime features.

### Companion Stack (API + UI)

```bash
./start-companion.sh
```

This starts FastAPI on `http://localhost:8001` and Next.js on `http://localhost:3000`. Press `Ctrl+C` to stop both.

To manage services manually:

```bash
# API
source .venv/bin/activate
python -m pmm.api.companion  # port 8001

# UI
cd ui
npm install
npm run dev                  # port 3000
```

---

## Provider Configuration

- `PMM_PROVIDER` selects the adapter (`openai`, `ollama`, `dummy`); defaults to OpenAI (`pmm/llm/factory.py:32`).
- `PMM_MODEL` chooses the chat model; for Ollama, set to your local model name.
- `OPENAI_BASE_URL` and `OPENAI_API_KEY` customise OpenAI endpoints when hosted.
- Embeddings use OpenAI by default; local providers can opt out and rely on text-only flows (`pmm/llm/factory.py:37`).

---

## Observability & API

The Companion API mirrors the runtime projections (`pmm/api/companion.py:95`):

- `GET /snapshot` – identity, latest events, directives.
- `GET /metrics` – IAS/GAS and stage; add `?detailed=true` for the CLI-equivalent snapshot.
- `GET /consciousness` – Living Identity dashboard payload.
- `GET /reflections`, `GET /commitments` – latest reflections and open commitments.
- `GET /traces` – reasoning trace summaries.
- `GET /traces/{session_id}` – trace drill-down.
- `GET /traces/stats/overview` – aggregate trace statistics.
- `POST /chat` – OpenAI-compatible streaming chat endpoint.
- `POST /events/sql` – read-only SQL (SELECT-only) over the ledger.

The UI layers these endpoints into chat, metrics, ledger, identity, and trace views (`ui/src/components/chat/chat.tsx:1`, `ui/src/components/chat/detailed-metrics-panel.tsx:1`).

---

## Development Workflow

- **Tests** – `pytest` (full) or targeted suites like `pytest tests/test_emergence_system.py`.
- **Lint** – `ruff check .` for Python, `npm run lint` for the UI.
- **Type Checks** – `mypy`.
- **Formatting** – `black`, `isort`, and Prettier (via Next.js).
- **Benchmarks & Diagnostics** – runtime emits `llm_latency`, `autonomy_tick`, and trace events; use `/events/sql` or the UI trace explorer to inspect.

---

## Project Layout (Selected)

```
pmm/
  api/companion.py           FastAPI surface for Companion UI + integrations
  runtime/
    loop.py                  Core runtime orchestrator + AutonomyLoop
    context_builder.py       Deterministic prompt assembly
    reflection.py            Reflection emission + gating
    metrics.py               IAS/GAS computation and telemetry
    snapshot.py              Ledger snapshot + caching helpers
  commitments/               Extraction, restructuring, and tracking
  storage/eventlog.py        Hash-chained SQLite ledger with tail caching
ui/                          Next.js 15 app (React 19, Tailwind 4)
tests/                       Pytest suites for runtime contracts
```

---

## Safety Defaults & Intentional Gaps

PMM v1.0 ships with conservative safety defaults:

- **Autonomous naming disabled** – Identity name proposals and adoptions require user confirmation. The runtime can generate proposals but won't auto-adopt without explicit approval (`pmm/runtime/loop.py:2038`).
- **Bounded trait evolution** – Trait updates use small, clamped deltas (±0.05 max) with strict invariant checks to prevent runaway drift (`pmm/storage/projection.py:19`, `pmm/runtime/self_evolution.py:1`).
- **Context-aware bandit partially wired** – Infrastructure is complete (stage stored in rewards, stage-filtered aggregation ready), but full stage-aware exploitation isn't used everywhere yet. See `CONTEXT-BANDIT-IMPLEMENTATION.md` for status.

These are design choices, not bugs. Enable autonomous naming or expand trait signals when you're ready for more aggressive self-modification.

---

## Data Integrity

- **Hash chaining** – Every event includes a SHA-256 hash of the previous event's content + metadata. This creates a tamper-evident chain.
- **Verification** – Hash chain verification is opt-in via `EventLog.verify_chain()` and used by runtime invariant checks (`pmm/runtime/invariants_rt.py:44`), not on every read.
- **Projection determinism** – Replaying the same ledger always produces the same identity, traits, and commitments (modulo timestamp-based TTL sweeps).

---

## Documentation

- **Implementation Details**: `IMPLEMENTATION-SUMMARY.md` - Phase 1 & 2 changes
- **Gap Analysis**: `BULLSHIT-ANALYSIS.md` - What was broken and fixed
- **Bandit Tracking**: `CONTEXT-BANDIT-IMPLEMENTATION.md` - Context-aware learning roadmap
- **Contributing**: `CONTRIBUTING.md` - Development guidelines

---

## License

See `LICENSE.md` for commercial and non-commercial licensing terms.
