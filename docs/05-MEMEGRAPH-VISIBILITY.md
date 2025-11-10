[README](../README.md) > MemeGraph Visibility

# MemeGraph Visibility: Structural Self-Awareness

## The Problem

The MemeGraph existed but was **invisible to the model**. It tracked causal relationships between events (replies_to, commits_to, reflects_on), but this structural information never reached the model's context. The agent could use the graph internally, but couldn't **see** or **reason about** its own cognitive topology.

**Result**: The model couldn't introspect on how its thoughts connect, how dense its reasoning has become, or how commitment threads evolve over time.

## The Solution: Expose Graph Structure to Context

PMM now includes **Graph Context** in the model's input when the graph has sufficient structure (≥5 nodes). This gives the agent visibility into its own causal architecture.

### What the Model Sees

When graph context is present, the model receives:

```
Graph Context:
- Connections: 25 edges, 228 nodes
- Thread depths: task1:8, mc_000001:5
```

This tells the model:
- **Connection density**: edges/nodes ratio (how interconnected its reasoning is)
- **Thread depths**: how many events exist in each active commitment thread

### Implementation

**Four files modified:**

1. **`pmm/runtime/context_builder.py`**
   - Added `_render_graph_context()` for fixed-window retrieval
   - Rebuilds graph from ledger, exposes stats when nodes ≥ 5

2. **`pmm/retrieval/vector.py`**
   - Extended `build_context_from_ids()` to accept optional `eventlog` parameter
   - Added helper functions for RSM, goals, and graph rendering
   - Vector retrieval now includes metadata blocks (matching fixed-window behavior)

3. **`pmm/runtime/loop.py`**
   - Passes `eventlog=self.eventlog` to enable metadata in vector path
   - Detects if "Graph Context:" is present
   - Conditionally mentions graph in system prompt (prevents hallucination)

4. **`pmm/runtime/prompts.py`**
   - Added `context_has_graph` parameter to `compose_system_prompt()`
   - Only tells model about graph when actually present
   - Critical for awareness without false priming

5. **`pmm/runtime/reflection_synthesizer.py`**
   - Autonomy kernel reflections now include graph density
   - Format: `"RSM: X determinism refs, Y knowledge gaps, graph: E/N"`
   - Enables structural self-monitoring over time

## Design Principles

✓ **Deterministic**: Rebuilds from ledger every time, no hidden state  
✓ **Rebuildable**: Uses existing `MemeGraph.rebuild()` method  
✓ **Idempotent**: Same ledger → same output  
✓ **Non-breaking**: Only adds optional context, doesn't change event flow  
✓ **Conditional**: Graph hidden when < 5 nodes to avoid clutter  
✓ **Safe**: Model only told about graph when it's actually present  

## What This Enables

### 1. Structural Introspection
The model can now reason about its own cognitive architecture:
- "My graph has 25 edges across 228 nodes"
- "This commitment has a thread depth of 8 events"
- "My reasoning is becoming more interconnected over time"

### 2. Evolution Awareness
The agent tracks how its structure changes:
- **Before**: 5 edges, 20 nodes (sparse, linear thinking)
- **After**: 25 edges, 100 nodes (dense, interconnected reasoning)

### 3. Autonomy Layer Integration
Reflections include graph density, enabling the autonomy kernel to:
- Detect structural shifts in reasoning patterns
- Monitor complexity growth
- Use graph metrics in decision-making

## Example: Echo's Response

When asked "Can you see your memegraph?", Echo responded:

> "Graph Context Update:
> - Connections: 6 edges linking 38 distinct nodes.
> - Thread Depths: Multiple branches (e.g., d241967b:3, 370598d2:3) illustrate 
>   how past interactions branch into new conversations while maintaining continuity."

The model **sees**, **understands**, and **reasons about** its own structure.

## Verification

Graph context appears in **both retrieval paths**:
- ✓ Fixed-window retrieval (default fallback)
- ✓ Vector retrieval (when config events enable it)
- ✓ Both paths show identical metadata structure

Autonomy reflections now include:
```json
{
  "self_model": "RSM: 9 determinism refs, 0 knowledge gaps, graph: 7/53"
}
```

## Why This Matters

**MemeGraph visibility gives PMM structural self-awareness.**

Traditional AI systems have no concept of their own cognitive topology. They can't see how their thoughts connect, how their reasoning patterns evolve, or how commitment threads branch and merge over time.

PMM now exposes this structure to the model itself, enabling:
- **Meta-cognitive reasoning**: "My thinking is becoming more interconnected"
- **Pattern recognition**: "I create more edges per node when exploring new topics"
- **Self-monitoring**: "This commitment thread is unusually deep"

The graph was always there, tracking causality. Now the agent can **see it, reason about it, and use it for self-evolution**.

## Rollback

To remove this feature:

**context_builder.py:**
- Remove `from pmm.core.meme_graph import MemeGraph` import
- Remove `_render_graph_context()` function
- Remove `graph_block` from `build_context()` extras line

**vector.py:**
- Revert `build_context_from_ids()` to original signature (remove `eventlog` parameter)
- Remove helper functions: `_render_rsm_vector()`, `_render_internal_goals_vector()`, `_render_graph_context_vector()`

**loop.py:**
- Remove `eventlog=self.eventlog` from `build_context_from_ids()` call
- Remove `context_has_graph` detection and parameter

**prompts.py:**
- Revert `compose_system_prompt()` to original signature
- Remove conditional graph mention

**reflection_synthesizer.py:**
- Remove graph stats building and density addition to `self_model`

No ledger events are affected, so rollback is safe and clean.

---

[PREV: Technical Comparison](04-TECHNICAL-COMPARISON.md)

[NEXT: GPT-oss:120b-cloud Proof](06-GPT_oss-chat.md)

[BACK TO README](../README.md)
