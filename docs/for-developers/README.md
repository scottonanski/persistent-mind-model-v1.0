# 🛠️ PMM for Developers

**Build with PMM: Integrate, extend, and contribute to persistent, auditable AI systems.**

## 🎯 Developer Paths

### 🚀 **Integration Developer**
**You want to:** Use PMM in your application or service
- **[API Integration Guide](api-integration.md)** - Connect to PMM programmatically
- **[Companion UI](companion-ui.md)** - Embed PMM's web interface
- **[Data Export](data-export.md)** - Extract conversation and evolution data

### 🔧 **Platform Developer**
**You want to:** Extend PMM's capabilities or modify its behavior
- **[Architecture Deep Dive](architecture-guide.md)** - Complete technical understanding
- **[Plugin System](plugin-system.md)** - Add new capabilities
- **[Configuration](configuration.md)** - Tune PMM's behavior

### 🤝 **Contributor**
**You want to:** Help improve PMM or fix bugs
- **[Development Setup](development-setup.md)** - Configure your environment
- **[Testing Strategy](testing.md)** - Write and run tests
- **[Code Style](code-style.md)** - Follow PMM's conventions

---

## 📚 Quick Developer Start

### 1. Get PMM Running
```bash
git clone https://github.com/scottonanski/persistent-mind-model.git
cd persistent-mind-model
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\activate
pip install -e .[dev]
export OPENAI_API_KEY=sk-...     # or set PMM_PROVIDER=ollama
python -m pmm.cli.chat  # Test basic functionality
```

### 2. Explore the APIs
```bash
# Start the companion server
python scripts/run_companion_server.py

# Test the APIs
curl http://localhost:8001/metrics
curl http://localhost:8001/events
curl http://localhost:8001/consciousness
```

### 3. Check the Web Interface
Visit `http://localhost:3000` to see PMM's companion UI in action.

---

## 🏗️ Architecture Overview

PMM is built on **event-driven architecture**:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Input    │ -> │   Event Log      │ -> │  State Models    │
│                 │    │  (SQLite + Hash) │    │  (Identity, etc) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Reflection     │ <- │  Autonomy Loop  │ -> │  Evolution      │
│  Engine         │    │  (60s cycle)    │    │  Engine         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Core Components
- **Event Log**: Append-only, hash-chained event storage
- **Autonomy Loop**: Background processing every 60 seconds
- **Reflection Engine**: Self-analysis and behavioral adaptation
- **Evolution System**: Personality and capability development
- **API Server**: REST endpoints for monitoring and control

---

## 🔧 Development Prerequisites

- **Python**: 3.8+
- **Node.js**: 18+ (for UI development)
- **Git**: Latest version
- **SQLite**: For database operations
- **Familiarity**: Event-driven systems, async programming

---

## 🚀 Getting Started as a Developer

1. **[Development Setup](development-setup.md)** - Environment and tools
2. **[Architecture Guide](architecture-guide.md)** - Understand the system
3. **[API Integration](api-integration.md)** - Connect programmatically
4. **[Testing](testing.md)** - Validate your changes

---

## 📖 Key Developer Concepts

### Event-Driven Everything
```python
# Every action creates an event
eventlog.append(kind="user_message", content=user_input)
eventlog.append(kind="reflection", content=analysis)
eventlog.append(kind="stage_progress", meta={"stage": "S4"})
```

### State as Projection
```python
# Current state is reconstructed from events
identity = build_identity_from_events(events)
personality = build_personality_from_events(events)
stage = determine_stage_from_events(events)
```

### Autonomy Through Reflection
```python
# Background loop processes and improves
while True:
    analyze_recent_events()
    generate_reflections()
    update_personality_traits()
    adapt_behavioral_parameters()
    time.sleep(60)
```

---

## 🧪 Development Workflow

1. **Fork & Clone** PMM repository
2. **Set up your environment** (see [Development Setup](development-setup.md))
3. **Run tests** to ensure everything works
4. **Make changes** following our patterns
5. **Add tests** for new functionality
6. **Submit a PR** with a clear description

---

## 📞 Developer Support

- **Issues**: [GitHub Issues](../../issues) - Bug reports and feature requests
- **Discussions**: [GitHub Discussions](../../discussions) - Technical questions
- **Architecture**: [Architecture Guide](architecture-guide.md) - Deep technical docs
- **API Docs**: [API Integration](api-integration.md) - Integration help

---

## 🎯 Developer Mission

**Help build the future of persistent AI agents.** PMM represents a shift from stateless tools to transparent, memory-rich systems. Your contributions shape how these agents learn responsibly and collaborate with people.

**Ready to contribute?** [Start here](development-setup.md) 🚀🤖🛠️
