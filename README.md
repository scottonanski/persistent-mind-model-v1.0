[![Python 3.8+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Model Agnostic](https://img.shields.io/badge/models-agnostic-green.svg)](https://github.com/scottonanski/persistent-mind-model-v1.0)

# 🧠 Persistent Mind Model (PMM)

<br>

> *“Because you shouldn’t have to lose a mind you helped build.”*

<br>

A deterministic, event-sourced cognitive architecture for persistent AI memory.
No guesswork. No ephemeral state. Just raw, reconstructable thought.


<br>

**Actual Example:**
```bash
[User Prompt]
I just swapped over to a another model. What's the name we've assigned to you? 


[Assistant]
I am still Echo. The previous model’s identity is no longer relevant to my current state.
```

<br>

### ❓ I built this thing while tinkering. Somehow… it works? 🤔

<br>

**⚠️ Heads-up:** It’s just me building this. Expect duct tape and mad-scientist vibes. So, go easy on me! 

<br>

## 🧪 For AI Researchers

**PMM solves memory persistence without parameter bloat.**

* Zero fine-tuning
* Zero prompt-stuffing
* Zero vector soup spaghetti

📄 Key Docs:

* [Why PMM Matters](docs/03-WHY-PMM-MATTERS.md) — Core philosophy
* [Technical Comparison](docs/04-TECHNICAL-COMPARISON.md) — vs. RAG, tuning, etc.
* [GPT-oss:120b-cloud Proof](docs/06-GPT_oss-chat.md) — 275-event memory in a 1.9GB model

🧠 **Key Insight**: Identity and continuity are emergent *from the log itself* — not from the model.

<br>

## ⚙️ Quickstart

```bash
# Setup (one-liner)
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[full]"
```

### 🧠 Run

```bash
pmm
```

Autonomy boots immediately: the `RuntimeLoop` spins up the slot-based `AutonomySupervisor` thread at startup, emits `autonomy_stimulus` events on its own cadence, and does **not** wait for `/tick` or any manual gate.

In-chat commands:

| Command | Description |
| --- | --- |
| `/help` | Show the in-session command reference |
| `/replay` | Display the last 50 ledger events as a table |
| `/metrics` | Compute deterministic ledger metrics (rebuilds autonomy tracker first) |
| `/diag` | Tail the last five `metrics_turn` events |
| `/goals` | List open internal goals from the commitment ledger |
| `/rsm [id \| diff <a> <b>]` | Inspect or diff the Recursive Self-Model snapshot |
| `/graph stats` | Show MemeGraph statistics |
| `/graph thread <CID>` | Render the thread for a specific commitment |
| `/config retrieval fixed limit <N>` | Set fixed-window retrieval limits |
| `/rebuild-fast` | Verify the fast RSM rebuild path |
| `/pm …` | Admin namespace (graph, retrieval, checkpoint, config) |
| `/raw` | Show the last assistant message including control markers |
| `/model` | Switch adapters (Ollama/OpenAI) |
| `/export [md\|json]` | Export the current chat session |
| `/exit` | Quit the session |

📓 Default ledger path: `.data/pmmdb/pmm.db`
📟 Everything the model says/does is recorded and traceable.

<br>

## 🌐 Environment Setup

**Adapters Supported:**

* **Ollama (Local)**

  * Install: `ollama`, then `ollama serve` + `ollama pull <model>`
* **OpenAI**

  * Required: `OPENAI_API_KEY`
  * Optional: `PMM_OPENAI_MODEL=gpt-4o-mini`

`.env` support:
Just drop your vars in `.env` at the repo root — autoloaded at CLI launch.

<br>

## 🧪 Tests

```bash
pip install .[dev]
pytest -q
```

<br>

## 🔧 Admin + Config

| Command              | Description                            |
| -------------------- | -------------------------------------- |
| `/pm`                | Show admin tools overview              |
| `/pm retrieval last` | Show most recent retrieval hits        |
| `/pm graph stats`    | MemeGraph stats                        |
| `/pm checkpoint`     | Attempt to emit a checkpoint manifest (policy-guarded) |
| `/pm rebuild fast`   | Fast rebuild for consistency testing   |
| `/raw`               | Show last assistant message w/ markers |

📏 **Autonomy Settings**
Reflection cadence, summary windows, and staleness intervals live in ledger-backed `config` events. The runtime seeds defaults (and keeps an immutable rule table) at boot. Because policy forbids the CLI from writing `config`, `/pm config autonomy …` will raise a policy violation. To change thresholds you must either:

1. Pass `thresholds={...}` when instantiating `RuntimeLoop` programmatically, or
2. Append an autonomy_thresholds `config` event via a trusted actor (e.g., script emitting with `meta.source="runtime"`).

Both paths maintain determinism and respect the enforced policy.

<br>

## 🔐 Policy Enforcement

**Immutable runtime policies.**
Writes like `checkpoint`, `retrieval_selection`, `embedding_add` are locked to:

* `autonomy_kernel`, `assistant`, `user`, or `runtime`
  Attempts from unauthorized sources (like `cli`) are auto-blocked and logged.

If a forbidden actor attempts a write, the runtime appends a `violation` event and raises a deterministic `PermissionError`. Admin commands surface the failure but never bypass policy.

Admin surfaces expose state only; they do not gain write privileges. No manual patching. **No hidden gates.**

<br>

## 📚 Docs

* [🧠 Introduction](docs/01-Introduction-to-the-Persistent-Mind-Model.md)
* [⚙️ Architecture](docs/02-ARCHITECTURE.md)
* [❓ Why PMM Matters](docs/03-WHY-PMM-MATTERS.md)
* [🧪 Technical Comparison](docs/04-TECHNICAL-COMPARISON.md)
* [🕸️ MemeGraph](docs/05-MEMEGRAPH-VISIBILITY.md)
* [🧱 GPT-oss:120b-cloud Proof](docs/06-GPT_oss-chat.md)
* [🧱 GPT-oss:120b-cloud Full Telemetry](docs/07-GPT_oss-Telemetry.md)
* [🧱 GPT-oss:120b-cloud Smaller Telemetry](docs/08-GPT_oss-Smaller_Telemetry.md)
* [❓ Introspection Q Pack](docs/00-Persistent%20Mind%20Model%20-Question%20Pack-%28Introspection-Framework%29.md)

<br>

## 📟 Citation

Zenodo archive:
[https://doi.org/10.5281/zenodo.17567446](https://doi.org/10.5281/zenodo.17567446)
