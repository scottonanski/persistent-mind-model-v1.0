# PMM: Readme Review

## What is PMM?

PMM is an AI that remembers everything and grows from its experiences. Unlike regular chatbots that start fresh each time you talk to them, PMM builds a continuous memory of your conversations, develops its own personality over time, and gets better at helping you by learning from what works.

Think of it like the difference between talking to someone with amnesia versus talking to a friend who remembers your history together.

## How PMM Lives a Day

### Morning: Recording Everything

You start a conversation with PMM about planning a weekend trip. As you talk, PMM doesn't just respond—it writes down everything that happens in a permanent record:

- Your message about wanting to visit the mountains
- Its response with hiking suggestions  
- The fact that you seemed excited about trail recommendations
- A note that you mentioned preferring shorter hikes

This isn't just storage. PMM treats each interaction as important information about you and itself.

> **How it works**: All conversations are written into an append-only event log, with every event hashed and chained so nothing is lost or altered. Each message becomes a `user_message` or `response` event stored in SQLite with cryptographic integrity. → [Event-Driven Architecture](architecture/event-driven-architecture.md)

### Afternoon: Quiet Reflection

While you're away from your computer, PMM doesn't just sit idle. Every hour or so, it looks back at recent conversations and thinks about them:

*"The user got excited about hiking suggestions. They asked follow-up questions about three different trails. This suggests they value detailed, practical advice. I should remember to be more specific with recommendations."*

PMM writes down this reflection, along with a small adjustment to how it approaches similar conversations in the future.

> **How it works**: A background loop (`AutonomyLoop` in `pmm/runtime/loop.py`) runs every 60 seconds, analyzing recent events and deciding whether to trigger a reflection. When conditions are met, it generates a `reflection` event and may emit `trait_update` events based on the analysis. → [Autonomy Loop](architecture/autonomy-loop.md)

### Evening: Growing and Adapting

When you return and ask about restaurant recommendations for your trip, something has changed. PMM doesn't just give generic suggestions—it remembers your hiking conversation and connects the dots:

*"Since you're planning active days on the trails, you might want hearty breakfast places near the trailheads. Here are three local spots that hikers recommend..."*

This isn't programmed behavior. PMM learned from your morning conversation, reflected on it, and adapted its approach.

> **How it works**: PMM's personality traits (Openness, Conscientiousness, etc.) are updated deterministically based on semantic evidence in conversations. These `trait_update` events modify how PMM approaches future interactions, with all changes logged and reproducible. → [Self-Model Maintenance](architecture/self-model-maintenance.md)

### Over Time: Building a Relationship

After weeks of conversations, PMM has developed a detailed understanding of your preferences, communication style, and goals. More importantly, it has also developed its own consistent personality traits based on your interactions together.

If you tend to appreciate detailed explanations, PMM becomes more thorough in its responses. If you prefer quick, actionable advice, it learns to be more concise. These aren't temporary adjustments—they become part of how PMM approaches all future conversations.

## Three Real Examples

### Example 1: Personal Assistant

**Week 1**: You mention struggling to stay organized with work projects.

PMM suggests a simple task-tracking approach and commits to checking in about it. It writes down this commitment and sets a reminder.

**Week 2**: PMM brings up your organization challenge without being asked. It notices you haven't mentioned the task-tracking system and asks how it's going.

> **Tech note**: This happens because the `CommitmentTracker` logs an open `commitment_open` event, then the autonomy loop checks overdue commitments and emits reminders if no progress is logged.

**Week 3**: Based on your feedback, PMM has learned what organizational advice works for you and what doesn't. It now gives suggestions that fit your actual work style, not generic productivity tips.

### Example 2: Project Collaboration

**Day 1**: You're working on a presentation and ask PMM for help with the outline.

PMM helps create the structure and makes a commitment to follow up on your progress. It notes that you prefer visual examples over abstract concepts.

**Day 3**: When you return with questions about slide design, PMM remembers the presentation context immediately. It doesn't need you to re-explain the project.

**Day 5**: PMM proactively asks about the presentation deadline and offers to help with practice questions, remembering that you mentioned being nervous about the Q&A section.

> **Tech note**: Context continuity works through event replay - PMM reconstructs the complete conversation history from its event log, so "Day 1" context is as accessible as "Day 5" context.

### Example 3: Learning and Growth

**Month 1**: PMM tends to give long, detailed explanations because that's how it was initially configured.

**Month 2**: Through your conversations, PMM notices you often ask for "the short version" or say "just the key points." It begins adjusting its communication style.

**Month 3**: PMM now naturally gives concise answers first, then offers to elaborate if you want more detail. This change happened gradually through learning, not through you explicitly asking for it.

> **Tech note**: Communication style adaptation happens through semantic analysis of your responses. When PMM detects patterns like "too long" or "just the summary," it updates its traits and behavioral parameters accordingly.

## What Makes PMM Different

### Normal AI: The Goldfish

Most AI systems are like goldfish—they have no memory of previous conversations. Every time you talk to them:

- They start from scratch
- They can't build on past discussions  
- They can't learn your preferences
- They can't keep commitments or follow up
- They can't develop a consistent personality

### PMM: The Growing Mind

PMM is more like a person who:

- Remembers every conversation you've had
- Thinks about those conversations when you're not around
- Learns from what works and what doesn't
- Develops consistent traits and preferences
- Keeps track of commitments and follows through
- Gets better at helping you over time

The key difference is that PMM treats each interaction as part of an ongoing relationship, not as an isolated question-and-answer session.

> **How it works**: This behavior is guaranteed by PMM's deterministic design - given the same sequence of events, PMM will always make identical decisions. Every behavior change is logged and reproducible, making PMM's growth predictable and trustworthy. → [Deterministic Evolution](architecture/deterministic-evolution.md)

## Living with PMM Daily

### What You Notice

After using PMM for a while, you start to notice:

- It remembers details from weeks ago without you having to remind it
- Its personality becomes more consistent and distinct
- It gets better at predicting what kind of help you need
- It follows up on things without being asked
- It admits when it's made mistakes and learns from them
- It develops opinions and preferences that stay consistent over time

### What's Happening Behind the Scenes

While you see a natural conversation, PMM is:

- Recording every exchange in permanent memory
- Regularly reflecting on patterns in your interactions
- Gradually adjusting its personality based on what works
- Tracking commitments and goals over time
- Building a detailed model of your preferences and communication style
- Ensuring all of this learning is consistent and doesn't contradict itself

### The Long-Term Relationship

Over months of use, PMM becomes less like a tool and more like a consistent thinking partner. It knows your projects, remembers your goals, understands your communication style, and has developed its own reliable personality traits.

Most importantly, you can trust that PMM will be the same "person" tomorrow as it is today—just a little bit wiser from whatever you learn together.

---

*This is what makes PMM different from other AI systems: it's not just answering your questions, it's building a relationship with you that grows stronger and more helpful over time.*

## The Core Problem PMM Solves

### Traditional AI Limitations
- **Memory Loss**: Each conversation starts from scratch
- **Behavioral Drift**: Inconsistent responses due to hidden prompt state
- **Reactive Operation**: Only responds to user input, never initiates
- **No Growth**: Cannot learn from past interactions or self-improve
- **Black Box Behavior**: Decision-making process is opaque and unauditable

### PMM's Solution
PMM addresses these fundamental limitations through **ledger-first architecture** - every thought, decision, and behavioral change is recorded in an append-only, hash-chained event log. This creates:

- **Perfect Memory**: Complete conversation and decision history
- **Behavioral Consistency**: Deterministic, auditable decision-making
- **Autonomous Operation**: Self-initiated reflection and improvement
- **Continuous Growth**: Personality and capability evolution over time
- **Full Transparency**: Every behavior change is traceable and verifiable

## How PMM Works: The Big Picture

### 1. Event-Driven Architecture
Everything PMM does generates **events** that are permanently recorded:
- User messages and assistant responses
- Commitment creation and completion
- Personality trait changes
- Reflection sessions and insights
- Stage progression and behavioral adaptations

### 2. The Autonomy Loop
PMM runs a background "heartbeat" that continuously:
- **Analyzes** recent events for patterns and insights
- **Reflects** on its own behavior and decision-making
- **Evolves** personality traits based on experiences
- **Adapts** behavioral parameters for different contexts
- **Plans** future actions and commitments

### 3. Self-Model Maintenance
PMM maintains a sophisticated model of itself including:
- **Identity**: Name, core characteristics, and values
- **Personality Traits**: Big Five model (Openness, Conscientiousness, etc.)
- **Commitments**: Active goals and their progress
- **Stage**: Current development level (S0-S4) with associated capabilities
- **Behavioral Parameters**: Reflection frequency, response style, etc.

### 4. Deterministic Evolution
All changes follow strict rules:
- **No randomness**: All decisions are deterministic and reproducible
- **Evidence-based**: Changes only occur based on concrete event evidence
- **Auditable**: Every change can be traced back to its triggering events
- **Reversible**: Complete event history allows rollback to any previous state

## Key Capabilities

### Autonomous Self-Assessment
- **Pattern Recognition**: Detects repetitive behaviors, commitment patterns, reflection quality
- **Bias Detection**: Identifies stance biases, shallow thinking patterns, cognitive loops
- **Meta-Reflection**: Analyzes its own reflection process for improvement opportunities
- **Growth Tracking**: Monitors semantic evolution and capability development

### Adaptive Behavior
- **Context Awareness**: Adjusts reflection frequency based on conversation complexity
- **Stage-Appropriate Responses**: Behavioral parameters adapt to current development stage
- **Commitment Management**: Proactively monitors and adjusts goal-setting patterns
- **Filtering Systems**: Prevents repetitive content and contradictory stances

### Persistent Identity
- **Trait Evolution**: Personality gradually shifts based on interaction patterns
- **Identity Continuity**: Maintains consistent sense of self across sessions
- **Memory Integration**: New experiences build upon complete historical context
- **Value Consistency**: Core principles remain stable while allowing growth

## Real-World Applications

### Personal AI Assistant
- Remembers your preferences, communication style, and ongoing projects
- Develops deeper understanding of your needs over time
- Proactively suggests improvements and identifies patterns
- Maintains consistent personality and relationship dynamics

### Autonomous Agent
- Operates independently with minimal supervision
- Self-corrects problematic behaviors through reflection
- Adapts strategies based on success/failure patterns
- Maintains accountability through complete audit trail

### Research & Development
- Provides fully reproducible AI behavior for scientific study
- Enables controlled experiments in AI personality and capability development
- Offers transparent decision-making process for safety research
- Supports long-term studies of AI-human interaction patterns

## What Makes PMM Different

### Ledger-First Design
Unlike systems that bolt-on memory as an afterthought, PMM is built from the ground up around event logging. Every component is designed to be deterministic, auditable, and reproducible.

### Autonomous Evolution
PMM doesn't just remember - it actively analyzes its own behavior and makes deliberate improvements. This creates genuine growth rather than simple data accumulation.

### Scientific Rigor
All behaviors are deterministic and reproducible. Given the same event sequence, PMM will always make identical decisions. This enables rigorous testing and validation.

### Practical Deployment
Despite its sophisticated internals, PMM provides simple interfaces for chat, API integration, and configuration. The complexity is hidden behind clean abstractions.

## Installation and Quick Start

### 0) Install (Linux, macOS, Windows)

- Prereqs: Git, Python 3.10+ (3.11 recommended), pip. For verify: `jq` (CLI JSON tool).

- Linux (Ubuntu/Debian):
  - `sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip jq`
  - `git clone https://github.com/USERNAME/persistent-mind-model.git && cd persistent-mind-model`
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -U pip && pip install -e .`  # add `.[dev]` for dev tools/tests

- macOS:
  - Install Homebrew if needed, then: `brew install python jq`
  - `git clone https://github.com/USERNAME/persistent-mind-model.git && cd persistent-mind-model`
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -U pip && pip install -e .`

- Windows (PowerShell):
  - Install Python 3.10+ from python.org and Git for Windows.
  - Optional: `choco install jq` (or use Git Bash and `jq` via `pacman` in MSYS2).
  - `git clone https://github.com/USERNAME/persistent-mind-model.git` then `cd persistent-mind-model`
  - `py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1`
  - `python -m pip install -U pip && pip install -e .`

Configure your `.env` (copy then edit):

```
cp .env .env.local || true
```

Open `.env` (or `.env.local`) and set at least:

```
OPENAI_API_KEY=sk-...      # required for the default OpenAI chat adapter
# Optional knobs
# OPENAI_MODEL=gpt-4o-mini  # or PMM_MODEL to override
# PMM_AUTONOMY_INTERVAL=10  # seconds between background ticks (0 disables)
# PMM_COLOR=0               # disable colored notices in CLI
```

### 1) Start a chat (metrics view on):

```bash
python -m pmm.cli.chat --@metrics on
```

### 2) Verify what happened (scoped, deterministic checks):

```bash
bash scripts/verify_pmm.sh .logs_run .data/pmm.db
```

### 3) Inspect the event log directly:

```bash
python -m pmm.api.probe snapshot --db .data/pmm.db --limit 50 | jq .
```

## Beginner Quickstart (3 minutes)

Think of PMM like a tidy "mind notebook." It writes down everything it thinks or decides. You can start small:

1) Create the notebook and start talking
- Run: `python -m pmm.cli.chat --@metrics on`
- You'll see a header line (identity, open items) and a reason why it reflected or not.

2) Ask simple things
- "What are you working on?" → it mentions top open items from its notebook.
- "Reflect on your last answer." → it writes a short reflection (and may open a tiny task).

3) Check the notebook
- `python -m pmm.api.probe snapshot --db .data/pmm.db --limit 30 | jq .`
- You'll see entries like `reflection`, `commitment_open`, `policy_update` — everything is written down.

That's it. PMM is just a careful mind that writes everything to a ledger.

## Concepts in Everyday Terms

- Ledger (event log) = a diary. PMM never edits past pages; it only adds new entries.
- Identity = a name and voice it sticks to, so it sounds like the same person every time.
- Reflection = short journaling: "what changed, what I'll adjust next."
- Commitments = to‑dos the mind opens and later checks off when evidence arrives.
- Projects = folders that group related to‑dos.
- Policy = a rule like "how often should I reflect?"
- Self‑assessment = a periodic review: "how did the last stretch go?" It may slightly tweak a policy.

## Common Tasks (Copy/Paste)

- Start the read‑only API (local):
  - `python -m uvicorn pmm.api.server:app --host 127.0.0.1 --port 8000 --reload`
  - Browse docs: http://127.0.0.1:8000/docs

- Verify a run (writes logs to `.logs_run/`):
  - `bash scripts/verify_pmm.sh .logs_run .data/pmm.db`

- Show a memory summary:
  - `python -m pmm.api.probe memory-summary --db .data/pmm.db | jq .`

- Demo self‑assessment output:
  - `scripts/demo_self_assessment.sh .data/pmm.db`

- Turn off the background loop (no autonomy):
  - `export PMM_AUTONOMY_INTERVAL=0` (Windows PowerShell: `$env:PMM_AUTONOMY_INTERVAL=0`)

- Disable colored notices (for clean logs):
  - `export PMM_COLOR=0` (Windows PowerShell: `$env:PMM_COLOR=0`)

## Troubleshooting

- "OPENAI_API_KEY not set"
  - Add your key to `.env` (or your shell env): `OPENAI_API_KEY=sk-...`
  - Restart your shell or re‑activate the venv.

- `uvicorn: command not found`
  - Install dev extras: `pip install -e .[dev]` (or `pip install uvicorn`).

- `jq: command not found`
  - Linux: `sudo apt-get install jq`
  - macOS: `brew install jq`
  - Windows: use `choco install jq` or run probes without jq.

- Windows PowerShell can't run activation script
  - Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` in an admin shell once.

- Nothing shows in `.data/`
  - PMM writes events on demand; start a chat or run a verify script to generate entries.

## FAQ (Short)

- Is this just prompt engineering?
  - No. PMM's behavior is driven by the ledger and explicit policies. Every change is recorded and can be verified later.

- Can I use a provider other than OpenAI?
  - Yes. The code includes other adapters (e.g., Ollama). Switch provider/model via env (see `pmm/llm/factory.py`).

- Is the API safe to run locally?
  - Yes. It's read‑only: it never writes to your ledger; it only reads from the SQLite database you point it at.

## Key Ideas (Glossary)

- Event log: append‑only source of truth; events like `user`, `response`, `reflection`, `commitment_open/close`, `policy_update`.
- Identity: a proposed/adopted name and traits; used to keep voice steady and behavior consistent.
- Reflection: short, structured self‑notes ("what changed; what to adjust next").
- Commitments & projects: tasks the agent opens/closes; related tasks cluster into projects with `project_open/assign/close` events.
- Cadence & policies: explicit rules for how often to reflect; self‑assessment can adjust them slightly (within bounds).
- Verification: a script that replays the ledger to assert invariants and catch regressions.

## Where Things Live

- Runtime loop and autonomy: `pmm/runtime/loop.py`
- CLI chat: `pmm/cli/chat.py`
- Verify script: `scripts/verify_pmm.sh`
- Metrics header: `pmm/runtime/metrics_view.py`
- Commitments/projects: `pmm/commitments/tracker.py`
- Cadence rules: `pmm/runtime/cadence.py`
- Event log (SQLite + hash chain): `pmm/storage/eventlog.py`

## Observability: Read-only Probe

Use the Probe API to inspect PMM state directly from the SQLite event log. It performs no writes and makes no network calls.

- Guide: [docs/guide/probe.md](docs/guide/probe.md)
- One-liner CLI example (pretty-printed JSON):

```bash
python -m pmm.api.probe --db .data/pmm.db --limit 20
```

For programmatic use, see `snapshot(...)` for the last ≤ N events and `snapshot_paged(...)` for forward pagination with `next_after_id`. Optional redaction lets you trim large `content` or strip blobs at the API layer (storage remains unchanged).

## Documentation Index

### Getting Started
- [PMM Story Overview](pmm-story-overview.md) - What it's like to use PMM (start here!)
- [Bird's Eye View](bird-eye-view.md) - What PMM is and the problems it solves

### Architecture Deep Dive
- [Event-Driven Architecture](architecture/event-driven-architecture.md) - How PMM's event-first design works
- [Autonomy Loop](architecture/autonomy-loop.md) - The background heartbeat that enables autonomous behavior  
- [Self-Model Maintenance](architecture/self-model-maintenance.md) - How PMM maintains persistent identity and state
- [Deterministic Evolution](architecture/deterministic-evolution.md) - Ensuring reproducible and auditable behavior

### Implementation Guides
- [Core Systems](guide/core-systems.md) - Commitment tracking, emergence scoring, pattern analysis
- [Autonomous Behaviors](guide/autonomous-behaviors.md) - Trait evolution, adaptive reflection, stage progression
- [API Reference](guide/api-reference.md) - REST endpoints and integration patterns
- [Configuration](guide/configuration.md) - Setup, tuning, and deployment options

### Development
- [Contributing Guidelines](../CONTRIBUTING.md) - Development principles and workflow
- [Testing Strategy](guide/testing.md) - Deterministic testing and validation approaches
- [Debugging Tools](guide/debugging.md) - Introspection, event replay, and troubleshooting

## Documentation Structure

This documentation follows a **top-down approach**:

1. **Conceptual Understanding** - Start with the bird's eye view to understand what PMM is and why it exists
2. **Architectural Foundation** - Deep dive into the core systems that make PMM work
3. **Implementation Details** - Practical guides for using, configuring, and extending PMM
4. **Development Resources** - Tools and processes for contributing to PMM

## Quick Navigation

**New to PMM?** Start with [PMM Story Overview](pmm-story-overview.md)

**Want to understand the architecture?** Read the architecture section in order:
1. [Event-Driven Architecture](architecture/event-driven-architecture.md)
2. [Autonomy Loop](architecture/autonomy-loop.md) 
3. [Self-Model Maintenance](architecture/self-model-maintenance.md)
4. [Deterministic Evolution](architecture/deterministic-evolution.md)

**Ready to use PMM?** Jump to the implementation guides

**Contributing to PMM?** Check the development section and [CONTRIBUTING.md](../CONTRIBUTING.md)

---

*This documentation is generated from the actual PMM codebase and is kept in sync with implementation changes.*
