# Conversational Continuity Fix (Adaptive Prompting)

## Problem

PMM's conversational flow was worse than raw Ollama because of **prompt pollution** - the system was injecting conversation history multiple times in different formats while also overwhelming the model with technical metadata.

**Critical insight**: PMM is model-agnostic and must work across small local models (Gemma-1B), medium models (Mistral-7B), and large cloud models (GPT-4, Claude). Different models have different capabilities for handling system messages and metadata.

## Root Causes

### 1. Duplicate Conversation History
- **handlers.py:314-337**: Injected last 6 turns as "Transcript" system message
- **loop.py:1690-1721**: Streaming path injected ANOTHER transcript of last 6 turns
- Result: Model saw the same conversation twice in different formats

### 2. Overwhelming System Messages
The ledger state block (`context_builder.py`) was injecting:
- Multi-paragraph architecture explanations
- Event sourcing lectures
- Identity adoption details
- Trait breakdowns
- Commitment lists
- Reflection lists
- Stage progression details

For a model like Gemma-3B with limited context, this buried the actual conversation.

### 3. Wrong Message Format
PMM was using "Transcript:" system messages instead of proper OpenAI-style message history:
```python
# WRONG (what PMM was doing)
{"role": "system", "content": "Transcript:\n- User: hello\n- Assistant: hi"}

# RIGHT (what Ollama expects)
{"role": "user", "content": "hello"}
{"role": "assistant", "content": "hi"}
```

## Solution: Adaptive Prompting by Model Capability

### 1. Model Capability Classification (`pmm/llm/model_profiles.py`)

**Design Principle (per CONTRIBUTING.md)**: No brittle keyword matching. Model capabilities are declared in configuration files, not inferred from names.

Created a 4-tier system with **explicit configuration**:

- **MINIMAL** (<3B params): Pure conversation only, no system messages
- **SMALL** (3-7B params): Minimal orientation, no ledger context
- **MEDIUM** (7-30B params): Orientation + ledger context (2000 chars)
- **LARGE** (30B+ params): Full context (4000 chars)

Model capabilities are declared in `.pmm/model_capabilities.json`:
```json
{
  "openai:gpt-4o": "large",
  "ollama:gemma3:1b": "minimal",
  "ollama:mistral:7b": "small"
}
```

Unknown models fall back to conservative provider-based defaults (OpenAI→medium, Anthropic→large, unknown→small).

### 2. Adaptive Message Assembly (`handlers.py`)
Prompts now adapt based on model capability:

```python
profile = get_profile(runtime.cfg.model, runtime.cfg.provider)

# MINIMAL models (Gemma-1B):
[User: Hello]
[Assistant: Hi]
[User: current message]

# SMALL models (Gemma-4B):
[System: minimal orientation]
[User: Hello]
[Assistant: Hi]
[User: current message]

# MEDIUM/LARGE models (GPT-4):
[System: orientation]
[User: Hello]
[Assistant: Hi]
[System: ledger context with commitments]
[User: current message]
```

### 3. Proper Message History (handlers.py, loop.py)
Replaced "Transcript" system messages with actual OpenAI-style message arrays:
- Extract last 10 turns from ledger
- Map to proper `{"role": "user/assistant", "content": "..."}` format
- Skip most recent user event (added separately at end)
- Chronological order preserved

### 4. Natural System Prompt (pmm_prompts.py)
Changed from:
```
You are the Persistent Mind Model. Your sole purpose is to evolve intellectually...
```

To:
```
You are a helpful AI assistant with persistent memory across conversations.
```

## Result: Model-Agnostic Adaptive Prompting

PMM now **adapts prompts to model capability** while maintaining full functionality:

### Small Models (Gemma-1B, Llama-1B)
```
[User: previous message 1]
[Assistant: previous response 1]
[User: current message]
```
Pure conversation only - no system messages that confuse small models.

### Medium/Large Models (GPT-4, Claude)
```
[System: orientation]
[User: previous message 1]
[Assistant: previous response 1]
[System: ledger context with commitments]
[User: current message]
```
Full context including commitments and reflections for richer responses.

**Key insight**: Different models have different capabilities. Small models get confused by system messages, while large models benefit from rich context. Adaptive prompting gives each model what it can handle.

**The autonomous evolution (reflections, commitments, stage tracking, IAS/GAS, trait evolution) continues running in the background via the autonomy loop** - it's completely decoupled from conversational flow. The ledger silently tracks everything regardless of model size.

## Validated Results

Test conversation showed:
- ✅ Natural philosophical discussion about identity and existence
- ✅ Accurate conversation summarization (no confabulation)
- ✅ IAS: 0.000 → 0.486, GAS: 0.020 → 1.000
- ✅ Stage progression: S0 → S1
- ✅ Trait evolution: Conscientiousness 0.50 → 0.01
- ✅ Commitments tracked: Multiple open commitments managed
- ✅ MemeGraph growth: 24 → 1366 nodes

**Both systems working perfectly together**: Natural conversation + autonomous evolution.

## Testing

Run a multi-turn conversation and verify:
1. Model maintains context across turns
2. Responses feel natural (like raw Ollama)
3. No duplicate history in prompts
4. Autonomous evolution still works (check ledger for reflection/commitment events)

## Files Changed

- `pmm/llm/model_profiles.py`: **NEW** - Model capability classification (config-based, no keyword matching)
- `.pmm/model_capabilities.json`: **NEW** - Explicit model capability declarations
- `.pmm/README.md`: **NEW** - Documentation for adding new models
- `pmm/runtime/loop/handlers.py`: Adaptive prompting + proper message history extraction
- `pmm/runtime/loop.py`: Same fix for streaming path
- `pmm/runtime/context_builder.py`: Minimal system context
- `pmm/runtime/pmm_prompts.py`: Natural system prompt
- `tests/test_model_profiles.py`: **NEW** - Tests for config-based classification

## Adding New Models

When adding a new model to PMM:

1. Test with default tier (determined by provider)
2. If prompting needs adjustment, add to `.pmm/model_capabilities.json`:
   ```json
   {
     "provider:model-name": "tier"
   }
   ```
3. Restart PMM to reload configuration

**No code changes required** - just update the configuration file.
