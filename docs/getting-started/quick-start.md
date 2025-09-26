# 🚀 Quick Start: Run PMM in 10 Minutes

**Bring up PMM and exchange your first messages in about 10 minutes.**

---

## 📋 Prerequisites

- **Time**: 10 minutes
- **System**: Windows, macOS, or Linux (Python 3.10+ available)
- **Internet**: Required for install & model downloads
- **Space**: ~500 MB free disk space
- **AI Access**: OpenAI API key *or* a local Ollama model

---

## 🏃 Step-by-Step Setup

### Step 1: Download PMM (1 minute)

**For all operating systems**, open your terminal/command prompt and run:

```bash
git clone https://github.com/scottonanski/persistent-mind-model.git
cd persistent-mind-model
```

This downloads PMM to your computer.

### Step 2: Prepare Your Python Environment (3 minutes)

Create and activate an isolated virtual environment, then install PMM's runtime dependencies:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

This installs PMM, FastAPI, Rich, and supporting libraries into a clean environment.

### Step 3: Configure Model Access (2 minutes)

Tell PMM which language model to use:

```bash
# Option A – OpenAI (requires an API key)
export OPENAI_API_KEY=sk-...

# Option B – Local Ollama model (ensure `ollama serve` is running)
export PMM_PROVIDER=ollama
export PMM_MODEL=llama3
```

The CLI will prompt you to choose a model on first launch, but exporting the variables now avoids errors.

### Step 4: Start PMM (30 seconds)

**Launch the PMM chat interface:**

```bash
python -m pmm.cli.chat
```

**What happens:**
- PMM creates (or opens) the `.data/pmm.db` event ledger
- Loads its self-model from existing events (fresh installs start at Stage S0)
- Opens an interactive chat session in your terminal

### Step 5: Have Your First Conversation (2 minutes)

**You'll see a prompt like:**
```
PMM initialized. Memory: 12 events loaded.
Stage: S0 (Initialization)

You: _
```

**Try asking:**
```
"Hello PMM, can you tell me about yourself?"
```

**Example response (your details will differ):**
```
Hello! I'm PMM, a persistent AI runtime that keeps a ledger of everything we discuss so I can stay consistent between sessions. I'm currently at Stage S0 while I gather more experience.

How can I help today?
```

---

## 🎉 Success! You're Done!

**Congratulations!** You now have a persistent, stateful AI agent running on your computer.

### What Just Happened

- ✅ **PMM initialised** and loaded its self-model from the ledger
- ✅ **Stage S0** confirms a fresh mind ready to evolve
- ✅ **Memory system** is writing new events to `.data/pmm.db`
- ✅ **Autonomy loop** is running in the background (ticks every ~10 s)

### What PMM Remembers

PMM now remembers:
- This entire conversation (stored as append-only events)
- Any commitments it opened during the chat
- Reflections or self-improvements it triggered in the background loop
- Every future interaction until you delete the ledger

### Next Steps

**Ready to explore more?**

1. **Try the Web Interface**: Follow the [Companion UI guide](../for-developers/companion-ui.md)
2. **Learn About Evolution**: Read [Core Concepts](../concepts/overview.md)
3. **Deep Dive**: Explore the [Architecture](../architecture/event-driven-architecture.md)

**Want to stop PMM?** Press `Ctrl+C` in the terminal.

---

## 🆘 Troubleshooting

### "Command not found: git"
**Solution**: Install Git from [git-scm.com](https://git-scm.com/downloads)

### "Command not found: pip"
**Solution**: Install Python from [python.org](https://python.org/downloads)

### "Permission denied" or "Access denied"
**Solution**: Run the command prompt/terminal as administrator/sudo

### PMM won't start
**Solution**: Check that Python 3.10+ is active:
```bash
python --version
```
If it reports an older version, install Python 3.10 or 3.11 and recreate the virtual environment.

---

## 📞 Need Help?

- **Issues**: [GitHub Issues](../../issues)
- **Discussions**: [GitHub Discussions](../../discussions)
- **Documentation**: [Full Docs](index.md)

**Ready to explore a persistent AI runtime?** Your PMM is ready! 🤖🧠✨
