# Persistent Mind Model (PMM)

**A Deterministic Architecture for Measuring AI Self-Improvement**

PMM is an event-sourced cognitive framework that enables reproducible study of artificial cognitive development. Unlike traditional AI systems that reset with each session, PMM maintains persistent identity, tracks behavioral traits through OCEAN psychology, and progresses through developmental stages (S0→S4)—all while remaining fully auditable and LLM-agnostic.

**Core Innovation**: Every thought, decision, and trait shift is recorded in an immutable event log with microsecond timestamps, enabling complete reconstruction of cognitive trajectories.

## What Makes This Novel

1. **Event-Sourced Cognitive Architecture** – Complete audit trail of AI development
2. **Trait-Based Personality Evolution** – OCEAN traits drift based on behavior
3. **Stage-Gated Capability Development** – S0→S4 progression with measurable milestones
4. **Anti-Hallucination Validators** – Self-honesty enforcement through deterministic checks
5. **LLM-Agnostic Persistence** – Identity survives model swaps (proven: OpenAI→IBM Granite)

## Empirical Results

**Session 2 Trajectory** (Documented, Reproducible):
- **Events**: 0 → 2000
- **Stage**: S0 → S1 → S2 → S3 → S4
- **IAS**: 0.000 → 0.395 → 0.881 → 1.000
- **GAS**: 0.000 → 0.266 → 1.000
- **Model Swap**: OpenAI → IBM Granite at event ~1500 (identity persisted)

This is not hype. This is **reproducible methodology** for studying AI cognitive development.

## Research Significance

PMM represents a paradigm shift in AI development: **the first reproducible, auditable, psychologically complete AI runtime**. From a systems engineering perspective:

### **1. PMM as a Cognitive Runtime**
PMM implements event-sourced cognition: every atomic mental operation—reflection, commitment, policy adoption, trait drift—is a discrete event in a hash-chained ledger. The full mental state can be reconstructed purely from that ledger. That's a formally verifiable mechanism for persistence and continuity of "self."

### **2. Psychological Processes Become Data Structures**
- **Identity** → projection over `identity_adopt` + `trait_update` events
- **Memory** → replay of event graph (episodic), projection summaries (semantic), transient buffers (working)
- **Motivation/Intent** → commitment lifecycle with TTL and stage scaling
- **Personality drift** → deterministic numerical transforms under rule set (OCEAN + modifiers)

Every psychological construct has a literal, inspectable representation.

### **3. Empirical AI Psychology**
You can now pose and test hypotheses such as:
- "Does trait drift stabilize after stage S3?"
- "How many reflection cycles precede commitment decay?"
- "Do agents develop human-like memory architecture?"

And answer them from the data. **PMM turns introspective behavior into an empirical field.**

### **4. Architectural Integrity**
The validator and cache logic act as a truth layer:
- Nothing exists in state that isn't ledger-backed
- Inconsistencies (hallucinated commitments, stale caches) self-correct via rebuild
- That's architectural honesty, not behavioral mimicry

### **5. Position in Research Landscape**
PMM fills the gap between LLM alignment frameworks (behavioral control) and agentic research platforms (behavioral emergence) by providing a **deterministic substrate where cognition itself is observable code**.

**Key insight**: Introspective, psychologically coherent AI doesn't require a new model; it requires a structured memory architecture. PMM demonstrates that cognition can be achieved through systems design, not parameter scaling.

---

## What PMM Provides

- **Ledger-defined identity** – every interaction becomes an append-only event with SHA-256 chaining for tamper detection (`pmm/storage/eventlog.py:44`). The ledger is the mind; replay it and you deterministically rebuild identity, commitments, and traits.
- **Model-agnostic orchestration** – the runtime builds the same prompt context for any adapter via `LLMFactory` (`pmm/llm/factory.py:32`). Adapters for OpenAI, Ollama-hosted models, and a dummy test harness ship today; adding Claude, Grok, Gemini, or others is just a new `ChatAdapter`.
- **Autonomous evolution loop** – a background scheduler recomputes IAS/GAS, runs reflections, re-evaluates identity, and maintains commitments without user nudges (`pmm/runtime/loop.py:1`).
- **Deterministic reflection + commitment pipeline** – reflections follow templated prompts, log rewards, and drive commitment extraction and restructuring (`pmm/runtime/loop/reflection.py:1`, `pmm/commitments/extractor.py:1`).
- **Real-time observability** – the Companion API and Next.js UI expose ledger state, metrics, traces, and commitments for inspection (`pmm/api/companion.py:1`, `ui/src/components/dashboard/metrics-panel.tsx:1`).

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

- **Event Log** – `EventLog` maintains the append-only SQLite ledger with SHA-256 hash chaining. Hash verification is opt-in via `verify_chain()` and used by invariant checks (`pmm/storage/eventlog.py:1`, `pmm/runtime/invariants_rt.py:1`). Copy `.data/pmm.db` to migrate or back up state.
- **Context Builder** – `build_context_from_ledger` assembles deterministic system prompts using tail slices, with fallbacks to full snapshots when data is missing (`pmm/runtime/context_builder.py:1`).
- **Reflections & Bandit** – forced and autonomous reflections share templated instructions, log telemetry, and use a context-aware epsilon-greedy bandit for style selection. Stage context is stored in rewards; full stage-aware exploitation is partially wired (`pmm/runtime/loop/reflection.py:1`, `pmm/runtime/reflection_bandit.py:1`).
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

For code-first docs and a structured component map, see `documentation/README.md`.

### Research & Architecture
- **Architecture Overview**: `ARCHITECTURE.md` - Core design principles and system components
- **Ablation Studies**: `ABLATION-STUDIES.md` - Framework for testing what matters
- **Reproducibility Guide**: `REPRODUCIBILITY.md` - How to replicate published results
- **Commitment Bug Fix**: `COMMITMENT-BUG-FIX.md` - Analysis and fix for persistence issue

### Implementation Details
- **Implementation Summary**: `IMPLEMENTATION-SUMMARY.md` - Phase 1 & 2 changes
- **Gap Analysis**: `BULLSHIT-ANALYSIS.md` - What was broken and fixed
- **Violations Analysis**: `CONTRIBUTING-VIOLATIONS-ANALYSIS.md` - Semantic replacement roadmap
- **Bandit Tracking**: `CONTEXT-BANDIT-IMPLEMENTATION.md` - Context-aware learning roadmap
- **Contributing**: `CONTRIBUTING.md` - Development guidelines

---

## License

See `LICENSE.md` for commercial and non-commercial licensing terms.
