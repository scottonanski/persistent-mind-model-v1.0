# Persistent Mind Model (PMM)

_A model-agnostic, event-sourced runtime that gives language models persistent memory, governance, and repeatable behaviour._

> **Heads up:** The codebase evolves quickly. The documentation set in `docs/` is the authoritative source for setup and architecture details; this README is a concise orientation.

---

## Why PMM?

Traditional chat wrappers forget context, hide their internal state, and drift unpredictably. PMM takes the opposite approach:

- **Every interaction is logged** to an append-only, hash-chained ledger (SQLite).
- **State is reconstructed deterministically** from that ledger, so behaviour is auditable and portable.
- **Adaptation is explicit and explainable**—reflections, policy updates, and trait nudges are emitted as events with evidence.
- **Model choice is a plug-in**: the same ledger can run on different LLM providers without retraining.

Think of PMM as a data layer plus control loop that turns an LLM into a persistent agent—one that remembers, self-assesses, and can justify how it changed over time.

---

## Core Capabilities

- 📓 **Ledger-first memory** – every user message, response, reflection, commitment, and policy update lives in the event log.
- 🧠 **Self-model projections** – the runtime maintains identity traits, active commitments, directives, and stage information via deterministic snapshots (LedgerSnapshot + MemeGraph).
- 🔄 **Autonomy loop** – a background loop evaluates recent events, emits reflections, chooses commitments, and adjusts cadence under strict gating rules.
- 📊 **Governance metrics** – IAS (Identity Autonomy Score), GAS (Goal Achievement Score), stage confidence, and curriculum hints drive policy updates and dashboards.
- 🔌 **Provider adapters** – OpenAI and local Ollama adapters ship today; new providers slot in by implementing the LLM adapter interface and wiring budgets/telemetry.
- 📡 **Read-only Companion API** – `/snapshot`, `/metrics`, `/consciousness`, `/reflections`, `/commitments`, and `/events/sql` expose the persistent state for tooling and UIs.

---

## Architecture at a Glance

```
User Input → EventLog.append(...) → LedgerSnapshot / MemeGraph → Autonomy Loop → Reflections & Policy Updates → Companion API / UI
```

Key modules:

| Component | Purpose |
|-----------|---------|
| `pmm/storage/eventlog.py` | Append-only, hash-chained ledger (SQLite) with append listeners |
| `pmm/runtime/loop.py` | Main runtime orchestrator + autonomy loop |
| `pmm/runtime/memegraph.py` | Graph projection for fast lookups (commitments, directives, stage) |
| `pmm/runtime/autonomy_integration.py` | Trait drift, stage behaviour, emergence, cadence, commitments |
| `pmm/api/companion.py` | Read-only FastAPI server used by tooling & UI |
| `docs/` | Living documentation (concepts, architecture, guides) |

---

## Model Providers (current & planned)

| Provider | Status | Notes |
|----------|--------|-------|
| OpenAI (GPT-4o, GPT-4o-mini, etc.) | ✅ Supported | Requires `OPENAI_API_KEY` |
| Ollama (local llama3, mistral, etc.) | ✅ Supported | Set `PMM_PROVIDER=ollama` |
| Other hosted APIs (Anthropic, Azure, self-hosted) | 🛠️ Planned | Implement adapter in `pmm/llm/adapters/` |

Adapter contracts enforce per-tick budgets, latency logging, and deterministic fallbacks so that swapping providers does not change the ledger semantics.

---

## Getting Started

Follow one of the docs guides depending on your role:

- **Quick evaluation:** [`docs/getting-started/quick-start.md`](docs/getting-started/quick-start.md)
- **Full dev environment:** [`docs/for-developers/development-setup.md`](docs/for-developers/development-setup.md)
- **Architecture deep dive:** [`docs/for-developers/architecture-guide.md`](docs/for-developers/architecture-guide.md)
- **Companion API usage:** [`docs/guide/api-reference.md`](docs/guide/api-reference.md)

Those guides cover environment creation, model configuration, autonomy controls, and tooling.

---

## Session Evidence

- 2025-09-26 — “Echo” transcript and analysis: [docs/sessions/2025-09-26-echo-session.md](docs/sessions/2025-09-26-echo-session.md)

---

## Common CLI Controls

Inside `python -m pmm.cli.chat`:

- `--@metrics on` / `off` – toggle the telemetry panel (IAS, GAS, stage, open commitments).
- `--@models` – switch provider/model interactively.
- `--@reflect` – request an immediate reflection (respecting gating).

The entire runtime state lives in `.data/pmm.db`; copy that file to migrate a mind to another machine or provider.

---

## Companion API Quick Reference

```bash
# Start the read-only API with hot reload
default_env="python scripts/run_companion_server.py"

# Health / metrics
curl -s http://localhost:8001/metrics | jq

# Snapshot (events + identity + directives)
curl -s http://localhost:8001/snapshot | jq '.events | length'

# Export reflections
db="tests/data/reflections_and_identity.db"
curl -s "http://localhost:8001/reflections?limit=10&db=$db" | jq
```

See [`docs/companion_api_guide.md`](docs/companion_api_guide.md) for more examples and SQL queries.

---

## Concepts Cheat Sheet

| Term | Plain description |
|------|-------------------|
| Ledger | Append-only diary; nothing is deleted or rewritten |
| Identity | Name + trait vector anchored in the ledger projections |
| Reflection | Short journal entry about recent behaviour / next steps |
| Commitment | TODO captured from reflections or user cues; tracked until evidence closes it |
| Stage | Development checkpoint (S0–S4) derived from IAS/GAS history |
| Policy | Tunable behaviour (reflection cadence, novelty thresholds, etc.) |

More detail lives in [`docs/concepts/overview.md`](docs/concepts/overview.md).

---

## Troubleshooting & Support

- **Troubleshooting playbook:** [`docs/guide/troubleshooting.md`](docs/guide/troubleshooting.md)
- **Configuration & deployment:** [`docs/guide/configuration-deployment.md`](docs/guide/configuration-deployment.md)
- **Issues / discussions:** [GitHub Issues](https://github.com/scottonanski/persistent-mind-model/issues) · [Discussions](https://github.com/scottonanski/persistent-mind-model/discussions)

---

## License

Dual-licensed (non-commercial / commercial). See [LICENSE.md](LICENSE.md) for full terms and the prior-art disclosure.

© 2025 Scott Onanski
