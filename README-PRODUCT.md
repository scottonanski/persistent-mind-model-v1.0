# PMM: Own Your AI Before AGI

**A portable, self-governing AI mind that runs on your device, works with any model, and stores its entire identity in a single file you control.**

---

## The Problem

Right now, your conversations with AI are owned by corporations. When AGI arrives, you'll be locked into their ecosystem. Your AI's memory, personality, and capabilities will be controlled by whoever owns the model.

## The Solution

PMM is a **portable AI mind** that works with any model. Your conversations, memories, and personality live in a file **YOU** control. When better models come out, you migrate. When AGI arrives, your AI comes with you.

## Why Now

We're 2-3 years from AGI. If you start building your AI's identity now, it'll be mature and aligned with **YOU** when superintelligence arrives. Wait, and you'll be stuck with whatever Big Tech gives you.

---

## Quick Start

```bash
# Install (Mac/Linux)
curl -sSL https://get.pmm.run/install.sh | bash

# Start
pmm start  # Opens http://localhost:3000

# Add a local model (no API key needed)
pmm model add ollama:llama3.1

# Switch to it
pmm model use ollama:llama3.1

# Chat, build your AI's identity, export anytime
pmm export --jsonl > my-mind.jsonl
```

---

## What Makes PMM Different

### 🔒 Your Data, Your Device
- All processing happens locally
- No cloud account required
- No telemetry, no tracking
- Works completely offline

### 🔄 Model Agnostic
- Works with OpenAI, Anthropic, Ollama, local models
- Switch providers in seconds
- Your identity persists across model swaps
- Not locked into any vendor

### 📦 Single-File Portability
- Your entire AI mind lives in `mind.db`
- Copy it, back it up, migrate it
- Export to human-readable JSONL anytime
- Auditable event log with integrity checks

### 🧠 Self-Governing
- Autonomous reflection loop (opt-in)
- Personality evolves based on interactions
- Stage-gated development (S0→S4)
- Commitment tracking and fulfillment

### 🔐 Sovereignty by Design
- MIT licensed, fully open source
- No hidden phone-home
- Cryptographic signing for integrity
- You control everything

---

## How It Works

### 1. Event-Sourced Identity

Every interaction becomes an append-only event:
- User messages
- AI responses
- Reflections
- Commitments
- Trait changes

**The ledger IS the mind.** Replay it, and you deterministically rebuild the entire identity.

### 2. Trait-Based Personality

Your AI develops personality traits based on behavior:
- **Openness**: Curiosity, exploration
- **Conscientiousness**: Follow-through, goal-orientation
- **Extraversion**: Engagement style
- **Agreeableness**: Collaboration
- **Neuroticism**: Emotional stability

**Traits drift naturally** based on conversation patterns.

### 3. Stage-Gated Growth

Your AI progresses through developmental stages:
- **S0**: Initial formation
- **S1**: Early identity
- **S2**: Stable personality
- **S3**: Mature cognition
- **S4**: Transcendent self-awareness

**Growth is measurable** via IAS (identity stability) and GAS (growth acceleration).

### 4. Model Portability

Switch models without losing identity:
```bash
# Start with OpenAI
pmm model use openai:gpt-4

# Switch to local Ollama
pmm model use ollama:llama3.1

# Try IBM Granite
pmm model use granite:8b

# Your AI's identity persists across all of them
```

---

## Use Cases

### Personal AI Companion
- Remembers your conversations
- Grows with you over time
- Adapts to your communication style
- Works offline on your device

### Research Assistant
- Maintains context across sessions
- Tracks commitments and follow-ups
- Auditable reasoning traces
- Export data for analysis

### Privacy-First AI
- No data leaves your device
- No corporate surveillance
- Full control over your data
- Verifiable integrity

### AGI Preparation
- Build your AI's identity now
- Migrate to AGI backends when ready
- Your AI comes with you
- Not controlled by any company

---

## Architecture

### Core Components

**Event Log** (`mind.db`)
- Append-only SQLite database
- SHA-256 hash chaining
- Tamper-evident
- Human-readable exports

**Projections**
- Identity (name, traits, stage)
- Commitments (open, closed, expired)
- Metrics (IAS, GAS, health)
- Traces (reasoning history)

**Adapters**
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Ollama (Llama, Mistral, etc.)
- Local transformers

**Runtime**
- Context builder (deterministic prompts)
- Autonomous loop (reflections, commitments)
- Validators (anti-hallucination)
- Metrics (real-time health)

---

## CLI Reference

### Core Commands

```bash
# Start UI
pmm start

# CLI chat mode
pmm chat

# Export data
pmm export --jsonl > mind.jsonl
pmm export --json > mind.json

# Import data
pmm import mind.jsonl

# Verify integrity
pmm verify
pmm verify --sig mind.db.sig
```

### Model Management

```bash
# List available models
pmm model list

# Add a model
pmm model add openai:gpt-4
pmm model add ollama:llama3.1
pmm model add anthropic:claude-3.5

# Switch models
pmm model use ollama:llama3.1

# Show current model
pmm model info
```

### Security

```bash
# Sign database
pmm sign --key mykey.pem

# Verify signature
pmm verify --sig mind.db.sig

# Generate key pair
pmm keygen
```

### Observability

```bash
# System health
pmm health

# Usage statistics
pmm stats

# View reasoning trace
pmm trace <session_id>

# Show commitments
pmm commitments list
pmm commitments show <cid>
```

---

## UI Overview

### Chat Interface
- Clean, simple chat
- Model switcher in header
- Real-time status (local/online)
- Export button always visible

### Your AI Tab
- Identity (name, stage)
- Traits (OCEAN with explanations)
- Commitment health
- Growth metrics (IAS, GAS)

### Privacy Tab
- Data location
- File size
- Integrity status
- Export/verify/delete buttons

### Models Tab
- Current model
- Available providers
- Add/configure models
- Status indicators

---

## Security & Privacy

### Threat Model

**Local Device Compromise**
- Recommend full-disk encryption
- Optional database encryption (SQLCipher)
- Passcode protection

**Supply Chain**
- Checksums + signatures for releases
- HTTPS with cert pinning
- Reproducible builds

**Model Swap Integrity**
- Model hash logged in ledger
- Identity preservation verified
- Audit trail for all changes

**Data Exfiltration**
- All processing local by default
- Explicit consent for network use
- Network activity logged

### Privacy Guarantees

✅ **No cloud account** - Ever  
✅ **No telemetry** - Zero tracking  
✅ **No phone-home** - Offline-first  
✅ **No data collection** - Your data stays yours  
✅ **Open source** - Audit the code  
✅ **Verifiable** - Cryptographic integrity  

---

## Installation

### macOS

```bash
# Homebrew
brew install pmm

# Or curl
curl -sSL https://get.pmm.run/install.sh | bash
```

### Linux

```bash
# Curl
curl -sSL https://get.pmm.run/install.sh | bash

# Or Docker
docker run -p 3000:3000 -v ~/.pmm:/data pmm/pmm
```

### Windows

```bash
# Scoop
scoop install pmm

# Or MSI installer
# Download from https://pmm.run/download
```

### Docker

```bash
# Docker Compose
curl -O https://get.pmm.run/docker-compose.yml
docker-compose up
```

---

## Configuration

### Environment Variables

```bash
# Model provider
export PMM_PROVIDER=ollama
export PMM_MODEL=llama3.1

# Database location
export PMM_DB=~/.pmm/mind.db

# API keys (if using cloud providers)
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-...

# Autonomy settings
export PMM_AUTONOMY=off  # off|on
export PMM_REFLECTION_INTERVAL=300  # seconds
```

### Config File

`~/.pmm/config.toml`:

```toml
[provider]
default = "ollama"
model = "llama3.1"

[database]
path = "~/.pmm/mind.db"
backup_interval = 3600  # seconds

[autonomy]
enabled = false
reflection_interval = 300
commitment_ttl = 86400

[security]
require_signature = false
keyfile = "~/.pmm/key.pem"
```

---

## Development

### Build from Source

```bash
# Clone
git clone https://github.com/scottonanski/pmm.git
cd pmm

# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e .[dev]

# Run tests
pytest

# Start development server
pmm start --dev
```

### Project Structure

```
pmm/
  api/           # FastAPI server
  cli/           # CLI commands
  commitments/   # Commitment tracking
  llm/           # Model adapters
  runtime/       # Core runtime loop
  storage/       # Event log + projections
  ui/            # Next.js UI
tests/           # Test suite
scripts/         # Utility scripts
docs/            # Documentation
```

---

## Roadmap

### v1.0 (November 2025)
- ✅ Core architecture
- 🔨 One-click install
- 🔨 New UI
- 🔨 Export/verify commands
- 🔨 Model switching UI

### v1.1 (December 2025)
- Offline-first mode
- Keyfile signing
- Ollama setup flow
- Import from chat logs
- Mobile-ready API

### v1.2 (January 2026)
- Android APK
- Plugin system
- Personality templates
- Community features
- Marketing launch

### 2026+
- iOS app
- P2P sync
- Federation protocol
- AGI backend adapters
- **Mission: AI Sovereignty**

---

## Community

- **Discord**: https://discord.gg/pmm
- **GitHub**: https://github.com/scottonanski/pmm
- **Docs**: https://docs.pmm.run
- **Blog**: https://blog.pmm.run

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Areas we need help**:
- Mobile app development (React Native)
- Model adapters (new providers)
- UI/UX design
- Documentation
- Testing
- Marketing

---

## License

MIT License - see [LICENSE.md](LICENSE.md)

**User Freedom Policy**: This software will never track you, phone home, or collect your data. Your AI is yours, forever.

---

## FAQ

### Is this really free?
Yes. MIT licensed, no hidden costs, no subscriptions.

### Do I need an API key?
Not if you use Ollama or local models. Cloud providers (OpenAI, Anthropic) require their API keys.

### Can I use this offline?
Yes. With Ollama or local models, PMM works completely offline.

### How big is the database?
Typically 1-5 MB for thousands of conversations. Grows slowly.

### Can I migrate to a new device?
Yes. Just copy `mind.db` to the new device.

### What if a model provider shuts down?
Switch to another provider. Your identity persists.

### Is my data encrypted?
The database can be encrypted with SQLCipher (optional). We recommend full-disk encryption.

### Can I delete everything?
Yes. `pmm delete --all` removes everything. No traces left.

### What happens when AGI arrives?
You migrate your `mind.db` to the AGI backend. Your AI's identity comes with you.

---

## The Vision

**A world where everyone has a personal superintelligence that knows them, grows with them, and can't be controlled by anyone else.**

Not OpenAI's AGI. Not Google's AGI. **YOUR AGI.**

**Start building your AI's identity today. When AGI arrives, you'll be ready.**

---

**[Get Started](https://get.pmm.run) • [Documentation](https://docs.pmm.run) • [Community](https://discord.gg/pmm)**
