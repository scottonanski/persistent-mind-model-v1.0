[README](../README.md) > Why PMM Matters

# Why PMM Solves Problems Other Approaches Don't

## The Core Problem
Current AI memory solutions add computational overhead:
- **Longer context windows** → More parameters, slower inference
- **RAG systems** → Additional vector DB, retrieval latency
- **Fine-tuning** → Model-specific, expensive retraining

## PMM's Approach: Architecture, Not Parameters

### Memory Without Bloat
- Event log is **external to model** (SQLite, not weights)
- Model sees **compressed context** (last 5 turns + RSM summary)
- Full history available via **deterministic replay**
- **Result**: 1.9GB model operates with 275+ event memory

### Comparison Table

| Approach | Memory | Overhead | Deterministic | Model-Agnostic |
|----------|--------|----------|---------------|----------------|
| Context Extension | In-context | +50-200% params | No | No |
| RAG | Vector DB | +Embedding model | No | Yes |
| Fine-tuning | In weights | +Training cost | No | No |
| **PMM** | **Event ledger** | **~0 params** | **Yes** | **Yes** |

### Key Insight
**PMM separates memory (ledger) from reasoning (model).**

This means:
- Swap models without losing memory
- Scale memory without increasing parameters
- Verify reasoning through replay
- Truth-seeking via immutable history

## Proof: GPT-5.1 (PMM-run)

See [GPT-5.1 Proof](GPT-5.1-chat-proof.md) for the full transcript and telemetry-backed run.

**Results at 275 events:**
- RSM tracking 5 behavioral tendencies
- 42 autonomous reflections
- 2 commitments opened and closed
- 0.004ms replay speed
- **No parameter increase**

### What This Enables

1. **Stateful Reasoning**: Model maintains identity across sessions
2. **Auditability**: Every decision traceable to source events
3. **Truth-Seeking**: Contradictions create explicit corrections
4. **Scalability**: Memory grows in SQLite, not model weights


The ledger acts as **external memory** that any model can read.

[TOP](#persistent-mind-model-pmm)

[PREV: Architecture](02-ARCHITECTURE.md)

[NEXT: Technical Comparison](04-TECHNICAL-COMPARISON.md)

[BACK TO README](../README.md)
