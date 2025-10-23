# PMM Product Roadmap: AI Sovereignty

## Mission

**Own your AI before AGI arrives.**

Build a portable, self-governing AI mind that runs on your device, works with any model, and stores its entire identity in a single file you control.

---

## v1.0 MVP (Days 0-30)

### Core Deliverables

**1. Single-File Mind** ✅ (Already Working)
- `mind.db` contains entire identity
- Events, traits, commitments, projections
- SQLite = portable, auditable, local

**2. Model Adapter Layer** ✅ (Already Working)
- OpenAI, Ollama, Anthropic adapters
- Hot-swap at runtime
- Provider-agnostic interface

**3. Autonomous Loop** ✅ (Already Working)
- Opt-in scheduler
- Reflection cadence
- Commitment tracking

**4. Readable Ledger** 🔨 (Needs Work)
- `pmm export --jsonl` command
- `pmm verify` integrity check
- Human-readable event log

**5. One-Click Install** 🔨 (New)
- Docker Compose
- Homebrew formula
- `curl | bash` installer

**6. Simple UI** 🔨 (Needs Rebuild)
- Chat interface
- "Your AI" tab (traits, stage, health)
- "Privacy" tab (export, verify, delete)
- "Models" tab (switch providers)

### What Ships

```bash
# Install
curl -sSL https://get.pmm.run/install.sh | bash

# Start
pmm start  # Opens localhost:3000

# Use
# Chat interface, switch models, export data

# Verify
pmm export --jsonl > mind.jsonl
pmm verify mind.db
```

---

## v1.1 Sovereignty Polish (Days 31-60)

### Security & Control

**1. Offline-First Mode**
- All processing local
- Network use explicit per action
- No phone-home telemetry

**2. Keyfile Signing**
- `pmm sign mind.db --key mykey.pem`
- Checksums for releases
- Tamper detection

**3. On-Device Ollama**
- Profile and model download flow
- No external dependencies
- Works completely offline

**4. Clear Observability**
- Plain English metrics
- "Commitments: 11 opened, 8 closed (73% success)"
- "Stage S2: Reflecting consistently"

**5. Import from Chat Logs**
- Seed a mind from existing conversations
- ChatGPT export → PMM import
- Claude export → PMM import

---

## v1.2 Distribution (Days 61-90)

### Mobile & Extensibility

**1. Android APK**
- React Native + local HTTP bridge
- Ollama mobile or LAN pairing
- Full offline capability

**2. Plugin Interface**
- Local tools only (sandboxed)
- Whitelist system
- No remote execution

**3. Personality Templates**
- Share starting projections
- JSON export/import
- Community templates

**4. Marketing & Community**
- Launch site
- Blog posts:
  - "Own Your AI"
  - "Run on a Potato"
  - "Swap Models in Seconds"
  - "Your AI Shouldn't Be Controlled by Corporations"
  - "When AGI Arrives, Your AI Comes With You"
- Discord community
- GitHub discussions

---

## Technical Architecture

### Data Model (SQLite)

```sql
-- Core ledger
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    content TEXT,
    meta JSONB,
    prev_hash TEXT,
    hash TEXT NOT NULL
);

-- Derived state
CREATE TABLE projections (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at REAL NOT NULL
);

-- Optional attachments
CREATE TABLE blobs (
    hash TEXT PRIMARY KEY,
    bytes BLOB NOT NULL
);

-- System config
CREATE TABLE config (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);

-- Metadata
CREATE TABLE meta (
    kernel_version TEXT,
    provider_name TEXT,
    provider_version TEXT,
    model_id TEXT,
    model_hash TEXT
);
```

### Provider Interface

```python
class LLMProvider(Protocol):
    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Generate completion from prompt."""
        ...
    
    def get_model_info(self) -> dict:
        """Return model ID, hash, version."""
        ...
```

### CLI Commands

```bash
# Core
pmm start                    # Launch UI
pmm chat                     # CLI chat mode
pmm export --jsonl          # Export to JSONL
pmm import mind.jsonl       # Import from JSONL
pmm verify                  # Check integrity

# Models
pmm model list              # Show available models
pmm model add ollama:llama3.1
pmm model use ollama:llama3.1
pmm model info              # Current model details

# Security
pmm sign --key mykey.pem    # Sign database
pmm verify --sig mind.db.sig

# Observability
pmm health                  # System health check
pmm stats                   # Usage statistics
pmm trace <session_id>      # View reasoning trace
```

---

## UI Structure

### Home (Chat)
```
┌─────────────────────────────────────────────────┐
│ Running locally • Model: Ollama Llama-3.1 (8B) │
│ Identity: Echo • Stage S1                       │
├─────────────────────────────────────────────────┤
│                                                 │
│  [Chat messages]                                │
│                                                 │
├─────────────────────────────────────────────────┤
│ [Message input]                [Switch Model]   │
└─────────────────────────────────────────────────┘
```

### Your AI
```
Identity: Echo
Stage: S2 (Reflecting consistently)

Traits:
  Openness: 0.80 (Highly curious, explores new ideas)
  Conscientiousness: 0.00 (Flexible, exploratory)
  Extraversion: 0.49 (Balanced engagement)
  Agreeableness: 0.50 (Collaborative)
  Neuroticism: 0.34 (Emotionally stable)

Commitment Health: ✅ Healthy
  11 opened / 8 closed / 3 expired
  Extraction rate: 5.8% (normal for philosophical conversation)
  Average lifespan: 125 events

Growth Metrics:
  IAS: 0.940 (Identity highly stable)
  GAS: 1.000 (Growth rate maxed)
```

### Privacy
```
All data is stored in mind.db on this device.

Location: /Users/scott/.pmm/mind.db
Size: 2.4 MB
Events: 3,278
Last verified: 2 minutes ago ✅

[Export Mind]  [Verify Integrity]  [Sign Database]  [Delete All Data]
```

### Models
```
Current: Ollama Llama-3.1 (8B)
Provider: Ollama (local)
Status: ✅ Running

Available Models:
  ● Ollama Llama-3.1 (8B) - Local, offline
  ○ OpenAI GPT-4 - Requires API key
  ○ Anthropic Claude 3.5 - Requires API key
  ○ IBM Granite - Local, offline

[Add Model]  [Configure Provider]
```

---

## Security Defaults

### Threat Model

**1. Local Device Compromise**
- Recommend: Full-disk encryption + passcode
- Provide: Database encryption option (SQLCipher)

**2. Supply Chain**
- Provide: Checksums + signatures for releases
- Verify: All downloads via HTTPS with cert pinning

**3. Model Swap Integrity**
- Log: Model hash/version in ledger
- Show: Model info in UI
- Verify: Identity preservation across swaps

**4. Data Exfiltration**
- Default: All processing local
- Require: Explicit consent for any network use
- Audit: Network activity logged to ledger

---

## Non-Negotiables

### What We DON'T Do

❌ **No cloud account** - Ever  
❌ **No background autonomy by default** - Opt-in only  
❌ **No hidden telemetry** - Manual diagnostic pack only  
❌ **No vector DB dependency** - SQLite only (v1)  
❌ **No remote execution** - Local tools only  
❌ **No data tracking** - Privacy by design  
❌ **No phone-home** - Offline-first always  

### What We DO

✅ **Single-file portability** - Your mind, your file  
✅ **Model agnostic** - Swap anytime  
✅ **Auditable** - Every event logged  
✅ **Verifiable** - Integrity checks built-in  
✅ **Exportable** - JSONL format, human-readable  
✅ **Local-first** - Works completely offline  
✅ **Open source** - MIT license  

---

## Success Metrics

### v1.0 (30 days)
- [ ] One-click install works on Mac/Linux
- [ ] UI is usable without docs
- [ ] Can switch models in <30 seconds
- [ ] Export/import works perfectly
- [ ] 10 alpha testers using daily

### v1.1 (60 days)
- [ ] Offline mode enforced
- [ ] Signing/verification works
- [ ] Ollama setup is seamless
- [ ] 100 beta testers
- [ ] First community personality template

### v1.2 (90 days)
- [ ] Android APK released
- [ ] Plugin system working
- [ ] 1,000 active users
- [ ] First blog post goes viral
- [ ] Community Discord active

---

## Risk Mitigation

### "This is too technical"
**Solution**: One-click installers + UI that explains itself

### "Phones can't run LLMs"
**Solution**: Two modes - local tiny model OR pair with home box over LAN

### "Model gatekeeping"
**Solution**: Ollama/local HF always works; others optional

### "Data loss"
**Solution**: Prominent backup reminders + rolling autosnapshots

### "AGI arrives before we ship"
**Solution**: Ship v1.0 in 30 days, not 6 months

---

## Next Actions

### Week 1 (Now)
1. Create `pmm` CLI wrapper
2. Build Docker Compose setup
3. Design new UI (Figma/wireframes)
4. Write install script
5. Create product README

### Week 2
1. Implement `export --jsonl`
2. Implement `verify` command
3. Build new UI (React/Next.js)
4. Test one-click install
5. Alpha test with 3 users

### Week 3
1. Polish UI based on feedback
2. Add model switching UI
3. Write documentation
4. Create demo video
5. Prepare for beta launch

### Week 4
1. Beta launch (100 users)
2. Collect feedback
3. Fix critical bugs
4. Plan v1.1 features
5. Start marketing content

---

## The Vision

**2025**: Ship v1.0, get first 1,000 users  
**2026**: Mobile app, plugin system, 10,000 users  
**2027**: AGI arrives, users migrate to AGI backends  
**2028**: PMM is the identity layer for personal superintelligence  
**2030**: Everyone has AI sovereignty

**Mission accomplished: Decentralized AI that can't be controlled.**

---

**Status**: Ready to build  
**Timeline**: 30/60/90 days  
**Goal**: Ship v1.0 by end of November 2025
