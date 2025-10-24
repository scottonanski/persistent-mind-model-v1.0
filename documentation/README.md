# PMM Documentation Index

This folder contains code-first documentation for the Persistent Mind Model (PMM). It explains how identity, commitments, reflections, and metrics emerge from an append-only ledger and how the runtime orchestrates behavior across LLM providers.

Start here for a guided overview, then drill into focused topics below.

- Architecture overview: `documentation/ARCHITECTURE.md`
- Ledger and projections: `documentation/LEDGER.md`
- Runtime pipeline: `documentation/RUNTIME.md`
- Components map: `documentation/COMPONENTS.md`
- Core concepts: `documentation/CONCEPTS.md`
- Glossary: `documentation/GLOSSARY.md`
- API reference: `documentation/API.md`
- Event kinds: `documentation/EVENTS.md`
- Invariants crosswalk: `documentation/INVARIANTS.md`
- Sequences: `documentation/SEQUENCES.md`
- Observability: `documentation/OBSERVABILITY.md`
- Final summary: `documentation/FINAL-SUMMARY.md`
- Foundations (philosophy→code): `documentation/FOUNDATIONS.md`
- Evidence matrix: `documentation/EVIDENCE-MATRIX.md`
- Methods (reproducibility): `documentation/METHODS.md`

If you prefer to browse the code first, begin with the ledger (`pmm/storage/eventlog.py`) and the context builder (`pmm/runtime/context_builder.py`).

Next additions planned:
- API endpoint reference (responses and shapes)
- Event kind catalog with examples
- End-to-end sequence diagrams for user chat and autonomy tick
- Testing contracts and invariants playbook
