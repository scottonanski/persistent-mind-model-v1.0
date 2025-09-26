# 🛠️ Development Setup

Follow these steps to get a full PMM development environment running on your machine.

## 1. Clone the repository

```bash
git clone https://github.com/scottonanski/persistent-mind-model.git
cd persistent-mind-model
```

**Requirements**
- Python 3.10+ (3.11 works great)
- Node.js 18+ (for the Companion UI)
- Git

## 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\activate
```

Keep this environment active while you work on PMM.

## 3. Install Python dependencies

For runtime work:

```bash
pip install -r requirements.txt
```

For full development tooling (formatters, linters, tests):

```bash
pip install -e .[dev]
```

## 4. Configure model access

Export an OpenAI key or point PMM at a local Ollama model:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Local model (requires `ollama serve`)
export PMM_PROVIDER=ollama
export PMM_MODEL=llama3
```

## 5. Optional: install UI dependencies

```bash
cd ui
npm install
cd ..
```

You can now run `npm run dev` inside `ui/` to launch the Companion UI.

## 6. Sanity-check the CLI

```bash
python -m pmm.cli.chat --@metrics on
```

You should see PMM start at Stage S0 and emit `autonomy_tick` events about every 10 seconds.

## 7. Start the Companion API (optional)

In another terminal (with the same virtual environment):

```bash
python scripts/run_companion_server.py
```

The API serves snapshots and metrics on `http://localhost:8001` for the UI and integrations.

You're ready to build! Head to [testing.md](testing.md) to validate changes, or [code-style.md](code-style.md) for formatting guidelines.
