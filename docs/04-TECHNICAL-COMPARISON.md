[README](../README.md) > Technical Comparison

# Technical Comparison: PMM vs Existing Approaches

## Memory Solutions Landscape

### 1. Extended Context Windows
**Examples**: Claude (200K), GPT-4 Turbo (128K)

**Approach**: Increase model's context window
**Cost**: ~Linear with context length
**Limitations**:
- Inference latency increases
- Memory constrained by context window
- Not truly persistent (resets each session)
- No auditability beyond context

### 2. RAG (Retrieval Augmented Generation)
**Examples**: LangChain, LlamaIndex

**Approach**: External vector database + retrieval
**Cost**: Embedding model + vector search
**Limitations**:
- Retrieval is non-deterministic (similarity-based)
- No causal reasoning (can't replay decisions)
- Requires separate vector DB infrastructure
- Hallucinations in retrieved context

### 3. Fine-tuning / LoRA
**Examples**: Model-specific training

**Approach**: Update model weights with new data
**Cost**: GPU hours, storage for checkpoints
**Limitations**:
- Model-specific (not transferable)
- Expensive to update
- No auditability (weights are opaque)
- Risk of catastrophic forgetting

### 4. Prompt Engineering
**Examples**: System prompts, few-shot examples

**Approach**: Carefully crafted instructions
**Cost**: Context tokens
**Limitations**:
- Limited by context window
- No true persistence
- No verification mechanism
- Brittle to prompt changes

## PMM's Architecture

### Event-Sourced Memory
```
User Input → Ledger Event (immutable)
         ↓
    Replay State
         ↓
  Model Inference (with compressed context)
         ↓
Assistant Output → Ledger Event
         ↓
    RSM Update → New behavioral metrics
```

**Key Differences:**
1. **Memory is external** (SQLite, not model)
2. **Replay is deterministic** (same events → same state)
3. **Verification built-in** (hash chains, causality)
4. **Model-agnostic** (swap models, keep ledger)

### Cost Analysis

For 1000 events over 30 days:

| Approach | Storage | Compute | Portability |
|----------|---------|---------|-------------|
| Extended Context | ~500KB/session | High (long context) | None |
| RAG | ~10MB vectors | Medium (retrieval) | Medium |
| Fine-tuning | ~5GB checkpoint | Very High (training) | Low |
| **PMM** | **~2MB SQLite** | **Low (short context)** | **Full** |

### Truth-Seeking Properties

**Traditional AI**: Model generates text → User trusts or doesn't  
**PMM**: Model generates text → Logged → Verified against ledger → Contradictions create explicit corrections

**Result**: Self-consistent reasoning over time

### For Research Teams

PMM enables:
- **Reproducible experiments** (replay from events)
- **Behavioral analysis** (RSM metrics over time)
- **Multi-agent systems** (cross-ledger references)
- **Long-term studies** (persistent identity)

All without modifying model architectures.


[TOP](#persistent-mind-model-pmm)

[PREV: Why PMM Matters](03-WHY-PMM-MATTERS.md)

[NEXT: IBM Granite 4 Proof](05-IBM-Granite-Chat.md)

[BACK TO README](../README.md)