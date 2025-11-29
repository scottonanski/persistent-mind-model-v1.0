[README](../README.md) > MemeGraph Visibility

# MemeGraph Visibility: Structural Self-Awareness

## The Problem

The MemeGraph existed but was **invisible to the model**. It tracked causal relationships between events (replies_to, commits_to, reflects_on), but this structural information never reached the model's context. The agent could use the graph internally, but couldn't **see** or **reason about** its own cognitive topology.

**Result**: The model couldn't introspect on how its thoughts connect, how dense its reasoning has become, or how commitment threads evolve over time.

## The Solution: Expose Graph Structure to Context

PMM now includes **Graph Context** in the model's input when the graph has sufficient structure (≥5 nodes). This gives the agent visibility into its own causal architecture.

### What the Model Sees

When graph context is present, the model receives a dedicated `## Graph` section in the prompt:

```
Graph Context:
- Connections: 25 edges, 228 nodes
- Thread depths: task1:8, mc_000001:5
```

This tells the model:
- **Connection density**: edges/nodes ratio (how interconnected its reasoning is)
- **Thread depths**: how many events exist in each active commitment thread

### Implementation

**Files modified:**

1. **`pmm/runtime/context_utils.py`** — `render_graph_context()` emits the `## Graph` section when the MemeGraph has ≥5 nodes (threads + connection density).
2. **`pmm/runtime/context_renderer.py`** — inserts the graph section into the context block alongside Concepts/Threads/State/Evidence.
3. **`pmm/runtime/loop.py` + `pmm/runtime/prompts.py`** — only tell the model about graph context when that section is actually present, preventing hallucinated graph awareness.
4. **`pmm/runtime/reflection_synthesizer.py`** — autonomy reflections still include graph density for self-monitoring.

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

In addition, the autonomy kernel now uses the MemeGraph structure directly to
identify **stalled commitments**:
- Open, non-internal commitments whose threads have not changed for more than
  `commitment_staleness` events are treated as "stalled".
- `decide_next_action()` prefers a `reflect` decision when stalled commitments
  exist, and points its evidence at the relevant commitment thread. This keeps
  attention focused on long-open intentions without introducing non-ledger
  state.

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

Vector retrieval is now **graph-augmented**:
- Top vector-selected message ids are expanded via MemeGraph neighbors
  (both directions, deterministically capped) before context is built.
- This keeps relevant commitment threads and nearby reflections together in the
  prompt, improving coherence while remaining fully ledger-derived.

Separately, the Concept Token Layer (CTL) maintains a **concept graph** over
semantic tokens (identity, policy, governance, topic, ontology) that appear in
the ledger. CTL has no static, hard-coded ontology; tokens become concepts only
when ledger events introduce them and they are recorded as `concept_define`,
`concept_bind_event`, or `concept_relate` entries. The autonomy loop
deterministically binds key system events (e.g., stability/coherence metrics,
policy updates, summaries, autonomy reflections) into CTL via explicit ledger
events. CTL is maintained automatically as an incremental projection in the
runtime loop and remains fully reconstructable from the ledger, giving PMM a
symbolic view of stability, governance, and autonomy behavior that complements
the event-level MemeGraph.

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

For human operators, the CLI also exposes structural views:
- `/graph stats` shows node/edge counts and per-kind frequencies.
- `/graph thread <CID>` prints the canonical commitment thread.
- `/graph explain <CID>` prints the minimal subgraph (thread + neighbors)
  that "explains" a commitment in terms of its local causal context.

The graph was always there, tracking causality. Now the agent can **see it, reason about it, and use it for self-evolution**.

## Rollback

To remove this feature:

**context_utils.py:**
- Remove `render_graph_context()` function
- Remove `from pmm.core.meme_graph import MemeGraph` import

**context_builder.py:**
- Remove `render_graph_context` from imports
- Remove `graph_block` from `build_context()` extras line

**vector.py:**
- Remove `render_graph_context` from imports
- Revert `build_context_from_ids()` to original signature (remove `eventlog` parameter)

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

[NEXT: Gemma‑3‑4B Proof](gemma3-4b-chat-proof.md)

[BACK TO README](../README.md)
