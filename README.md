[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Model Agnostic](https://img.shields.io/badge/models-agnostic-green.svg)]()

**Event-sourced cognitive architecture for persistent AI memory**

## I was tinkering around and built this. Somehow it works??? 🤔

**_Go easy on me. I'm just one guy building this in my free time._** 🤣

---

# Persistent Mind Model (PMM)

> *"Because you shouldn't have to lose a mind you helped build."*

Persistent Mind Model (PMM) is a deterministic, ledger‑recall system. Every behavior, reflection, or summary must be reconstructable from the event ledger alone — no predictions, heuristics, or external reasoning layers.

## For AI Researchers

PMM solves memory persistence without parameter overhead:

- **[Why PMM Matters](docs/03-WHY-PMM-MATTERS.md)** - Core problem and solution
- **[Technical Comparison](docs/04-TECHNICAL-COMPARISON.md)** - vs RAG, context extension, fine-tuning
- **[Granite 4 Proof](docs/IBM-Granite-Chat.md)** - 1.9GB model with 275-event memory

**Key Result**: Deterministic memory that scales independently of model size.

**For Grok Integration**: See integration pseudocode in Technical Comparison.

- Quick start (one-time, installs EVERYTHING)
  1. `python3 -m venv .venv && source .venv/bin/activate`
  2. `pip install -e ".[full]"`   # installs package + all optional runtime deps

- Run
  - `pmm`  # choose a model; use in‑chat commands `/replay`, `/metrics`, `/diag`, `/goals`, `/rsm`, `/exit`
  - The ledger stores at `.data/pmmdb/pmm.db` by default.

Environment / prerequisites
- For Ollama adapter: install `ollama` and pull at least one local model (`ollama serve` then `ollama pull <model>`)
- For OpenAI adapter: set `OPENAI_API_KEY` (the full install already includes the OpenAI SDK)

Environment
- `OPENAI_API_KEY` — your OpenAI API key
- `PMM_OPENAI_MODEL` or `OPENAI_MODEL` — model name (e.g., `gpt-4o-mini`)

Dotenv
- If a `.env` file exists at the repo root, it is auto‑loaded on CLI start (via python‑dotenv).

- Tests
  - `pip install .[dev]`
  - `pytest -q`

Optional helper scripts
- `./scripts/bootstrap.sh` sets up a venv and installs deps in one step.
- `./scripts/run-tests.sh` installs dev deps and runs tests.

See `STATUS.md` for sprint progress and `CONTRIBUTING.md` for development rules.

Admin (/pm)
- `/pm` — show admin topics and examples
- Retrieval
  - `/pm retrieval config fixed limit <N>`
  - `/pm retrieval config vector limit <N> model hash64 dims 64`
  - `/pm retrieval last` (shows last `retrieval_selection` ids + scores)
- Graph
  - `/pm graph stats`
  - `/pm graph thread <CID>`
- Checkpoint + Rebuild
  - `/pm checkpoint` (emit checkpoint_manifest; idempotent)
  - `/pm rebuild fast` (verify fast rebuild equivalence)
- Autonomy thresholds (ledger-bound)
  - `/pm config autonomy reflection_interval=<N> summary_interval=<N> commitment_staleness=<N> commitment_auto_close=<N>`
- Raw output
  - `/raw` (show last assistant message with markers; UI hides markers by default)

### Policy Enforcement

PMM enforces an immutable runtime policy set by the autonomy kernel. Sensitive ledger writes (`config`, `checkpoint_manifest`, `embedding_add`, `retrieval_selection`) are only allowed from trusted sources: `autonomy_kernel`, `assistant`, `user`, or `runtime`.

Attempts by forbidden sources (like `cli`) are blocked and recorded as `violation` events.

Admin commands remain read-only for inspection (`/pm retrieval status`, `/pm graph stats`, etc). All maintenance is handled autonomously—no manual ops required.

Docs
- [Introduction](./docs/01-Introduction-to-the-Persistent-Mind-Model.md)
- [Architecture overview](./docs/02-ARCHITECTURE.md)
- [Why PMM Matters](./docs/03-WHY-PMM-MATTERS.md)
- [Technical Comparison](./docs/04-TECHNICAL-COMPARISON.md)
- [IBM Granite 4 Proof](./docs/05-IBM-Granite-Chat.md)
- [Introspection Question Pack](./docs/00-Persistent%20Mind%20Model%20-Question%20Pack-(Introspection-Framework).md)



