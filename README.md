[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Model Agnostic](https://img.shields.io/badge/models-agnostic-green.svg)](https://github.com/scottonanski/persistent-mind-model-v1.0)

# 🧠 Persistent Mind Model (PMM)

> *“Because you shouldn’t have to lose a mind you helped build.”*

A deterministic, event-sourced cognitive architecture for persistent AI memory.
No guesswork. No ephemeral state. Just raw, reconstructable thought.

<br>

### ❓ What Is This? I built this thing while tinkering. Somehow… it works? 🤔

<br>

**⚠️ Heads-up:** It’s just me building this. Expect duct tape and mad-scientist vibes. So, go easy on me! 


<br>

**Actual Example:**
```bash
[User Prompt]
I just swapped over to a another model. What's the name we've assigned to you? 


[Assistant]
I am still Echo. The previous model’s identity is no longer relevant to my current state.
```

<br>

## 🧪 For AI Researchers

**PMM solves memory persistence without parameter bloat.**

* Zero fine-tuning
* Zero prompt-stuffing
* Zero vector soup spaghetti

📄 Key Docs:

* [Why PMM Matters](docs/03-WHY-PMM-MATTERS.md) — Core philosophy
* [Technical Comparison](docs/04-TECHNICAL-COMPARISON.md) — vs. RAG, tuning, etc.
* [Granite 4 Proof](docs/05-IBM-Granite-Chat.md) — 275-event memory in a 1.9GB model

🧠 **Key Insight**: Identity and continuity are emergent *from the log itself* — not from the model.

---

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

In-chat commands:

* `/replay`, `/metrics`, `/rsm`, `/goals`, `/diag`, `/exit`

📓 Default ledger path: `.data/pmmdb/pmm.db`
📟 Everything the model says/does is recorded and traceable.

---

## 🌐 Environment Setup

**Adapters Supported:**

* **Ollama (Local)**

  * Install: `ollama`, then `ollama serve` + `ollama pull <model>`
* **OpenAI**

  * Required: `OPENAI_API_KEY`
  * Optional: `PMM_OPENAI_MODEL=gpt-4o-mini`

`.env` support:
Just drop your vars in `.env` at the repo root — autoloaded at CLI launch.

---

## 🧪 Tests

```bash
pip install .[dev]
pytest -q
```

---

## 🔧 Admin + Config

| Command              | Description                            |
| -------------------- | -------------------------------------- |
| `/pm`                | Show admin tools overview              |
| `/pm retrieval last` | Show most recent retrieval hits        |
| `/pm graph stats`    | MemeGraph stats                        |
| `/pm checkpoint`     | Emit an idempotent checkpoint manifest |
| `/pm rebuild fast`   | Fast rebuild for consistency testing   |
| `/raw`               | Show last assistant message w/ markers |

📏 **Autonomy Settings**
Configure reflection cadence, summary windows, and staleness intervals:

```bash
/pm config autonomy reflection_interval=10 summary_interval=5 ...
```

---

<br>

## 🔐 Policy Enforcement

**Immutable runtime policies.**
Writes like `checkpoint`, `retrieval_selection`, `embedding_add` are locked to:

* `autonomy_kernel`, `assistant`, `user`, or `runtime`
  Attempts from unauthorized sources (like `cli`) are auto-blocked and logged.

All admin commands = read-only.
No manual patching. **No hidden gates.**

---

## 📚 Docs

* [🧠 Introduction](docs/01-Introduction-to-the-Persistent-Mind-Model.md)
* [⚙️ Architecture](docs/02-ARCHITECTURE.md)
* [❓ Why PMM Matters](docs/03-WHY-PMM-MATTERS.md)
* [🧪 Technical Comparison](docs/04-TECHNICAL-COMPARISON.md)
* [🧱 Granite 4 Proof](docs/05-IBM-Granite-Chat.md)
* [🕸️ MemeGraph](docs/06-MEMEGRAPH-VISIBILITY.md)
* [❓ Introspection Q Pack](docs/00-Persistent%20Mind%20Model%20-Question%20Pack-%28Introspection-Framework%29.md)

---

## 📟 Citation

Zenodo archive:
[https://doi.org/10.5281/zenodo.17567446](https://doi.org/10.5281/zenodo.17567446)
