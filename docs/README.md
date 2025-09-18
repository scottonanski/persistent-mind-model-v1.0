# PMM Documentation

## Table of Contents

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
