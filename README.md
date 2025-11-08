# Persistent Mind Model

> Persistent Mind Model (PMM) is a deterministic, ledger‑recall system. Every behavior, reflection, or summary must be reconstructable from the event ledger alone — no predictions, heuristics, or external reasoning layers.

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
- [Introduction](docs/01-Introduction-to-the-Persistent-Mind-Model.md)
- [Architecture overview](docs/02-ARCHITECTURE.md)


