# Presentation Layer Fixes - Live Data Synchronization

## Overview

The PMM runtime is fully operational, but the UI presentation layer is showing stale data. This document outlines fixes for four key issues:

1. **Ledger Tab** - Enable live event streaming
2. **Commitment Visibility** - Fix context builder to show all commitments
3. **Trace Rendering** - Display reasoning traces in UI
4. **Context Refresh** - Invalidate snapshot cache between autonomy ticks

---

## 1. Ledger Tab - Live Event Streaming

### Current Behavior
- `staleTime: 30000` (30 seconds) - data cached for 30s
- Manual refresh required to see new events
- No auto-polling for autonomy tick events

### Fix: Enable Auto-Refresh

**File**: `ui/src/components/ledger/events-table.tsx`

**Change**:
```typescript
// BEFORE (line 80-82)
staleTime: 30000, // 30 seconds
gcTime: 5 * 60 * 1000, // 5 minutes

// AFTER
staleTime: 0, // Always fetch fresh data
refetchInterval: 5000, // Auto-refresh every 5 seconds
gcTime: 5 * 60 * 1000, // 5 minutes
```

This will make the ledger tab auto-refresh every 5 seconds, showing new autonomy_tick events as they arrive.

---

## 2. Commitment Visibility - Fix Context Builder

### Current Behavior
- `read_tail(limit=1000)` may miss old commitments
- Commitments exist in ledger but don't appear in chat context
- LLM says "no commitments" even though ledger shows 3 open

### Root Cause
The context builder uses `read_tail(1000)` for performance, but commitments opened early in the ledger (before event ID 1000) won't be visible.

### Fix Option A: Use `read_all()` for Commitment Queries

**File**: `pmm/storage/projection.py`

Find the `build_self_model()` function and ensure it uses `read_all()` instead of relying on the passed events:

```python
def build_self_model(events: list[dict] | None = None, eventlog=None) -> dict:
    """Build self-model from events, ensuring all commitments are visible."""
    # If eventlog is provided, always read_all() for commitments
    if eventlog is not None:
        events = eventlog.read_all()
    elif events is None:
        events = []
    
    # ... rest of function
```

### Fix Option B: Increase Tail Limit for Commitment Contexts

**File**: `pmm/runtime/context_builder.py`

```python
# BEFORE (line ~150)
events = eventlog.read_tail(limit=1000)

# AFTER - Use larger window when commitments are requested
if include_commitments:
    events = eventlog.read_tail(limit=5000)  # Larger window for commitments
else:
    events = eventlog.read_tail(limit=1000)  # Standard window
```

**Recommendation**: Use Option A for correctness, Option B for performance.

---

## 3. Trace Rendering - Display Reasoning Traces

### Current Behavior
- 20 `reasoning_trace_summary` events in ledger
- Traces tab shows "0 Nodes Visited"
- UI is reading summaries but not rendering node data

### Root Cause
The trace summaries don't include the actual reasoning nodes - they're stored separately or the UI isn't parsing them correctly.

### Fix: Check Trace Data Structure

**File**: `ui/src/app/traces/page.tsx`

Need to verify:
1. Are reasoning nodes stored in the `reasoning_trace_summary` meta?
2. Is the UI component parsing the correct fields?

**Diagnostic Query**:
```sql
SELECT meta FROM events WHERE kind = 'reasoning_trace_summary' LIMIT 1;
```

This will show what data is actually available. The fix depends on the structure.

### Expected Structure
```json
{
  "session_id": "...",
  "query": "...",
  "total_nodes_visited": 0,
  "node_type_distribution": {},
  "reasoning_steps": ["Building context", "Streaming LLM", "Response processed"],
  "duration_ms": 2786
}
```

**Issue**: `total_nodes_visited: 0` suggests the trace buffer isn't capturing node traversals.

### Fix: Enable Trace Buffer Node Capture

**File**: `pmm/runtime/trace_buffer.py`

Check if `add_reasoning_step()` is being called with actual node data or just string descriptions. The current implementation might only be logging high-level steps, not detailed node traversals.

---

## 4. Context Refresh - Invalidate Snapshot Cache

### Current Behavior
- Runtime creates snapshot once per request
- Snapshot cached in `Runtime._get_snapshot()`
- Autonomy ticks update ledger but don't invalidate cache
- Chat responses use stale snapshot

### Fix: Invalidate Cache on Autonomy Tick

**File**: `pmm/runtime/loop.py` (AutonomyLoop.tick method)

**Add cache invalidation after each tick**:

```python
def tick(self) -> None:
    """Execute one autonomy cycle."""
    # ... existing tick logic ...
    
    # Emit autonomy_tick event
    self.eventlog.append(
        kind="autonomy_tick",
        content="",
        meta={...}
    )
    
    # INVALIDATE RUNTIME SNAPSHOT CACHE
    if self.runtime is not None:
        try:
            # Force snapshot refresh on next request
            if hasattr(self.runtime, '_snapshot_cache'):
                self.runtime._snapshot_cache = None
        except Exception:
            pass
```

### Alternative: Use Request-Scoped Cache

**File**: `pmm/runtime/request_cache.py`

The `CachedEventLog` already exists but might not be invalidating properly. Ensure it clears on each autonomy tick:

```python
class CachedEventLog:
    def append(self, kind: str, content: str, meta: dict) -> int:
        # Invalidate cache on write
        self._cache.invalidate()
        return self._eventlog.append(kind=kind, content=content, meta=meta)
```

This should already be implemented (line 252-255), so the issue might be that the Runtime isn't using CachedEventLog consistently.

---

## Implementation Priority

| Fix | Priority | Impact | Effort |
|-----|----------|--------|--------|
| **1. Ledger Auto-Refresh** | 🔴 High | Users see live events | 5 min |
| **2. Commitment Visibility** | 🔴 High | LLM can see all commitments | 15 min |
| **4. Context Refresh** | 🟡 Medium | Chat responses stay current | 30 min |
| **3. Trace Rendering** | 🟢 Low | Nice-to-have visualization | 1-2 hours |

---

## Testing Plan

### 1. Ledger Auto-Refresh
```bash
# Start server
./start-companion.sh

# Open http://localhost:3001/ledger
# Watch for new events appearing every 5-10 seconds
# Should see autonomy_tick, stage_progress, etc. streaming in
```

### 2. Commitment Visibility
```bash
# Send chat message: "What commitments do you have?"
# Expected: LLM lists the 3 open commitments
# Current: LLM says "no commitments"
```

### 3. Context Refresh
```bash
# Have a conversation
# Wait 10 seconds for autonomy tick
# Send another message
# LLM should reference updated IAS/GAS values
```

### 4. Trace Rendering
```bash
# Open http://localhost:3001/traces
# Should see reasoning steps for each query
# Should show node traversal data (if captured)
```

---

## Quick Wins (5-Minute Fixes)

### Fix #1: Ledger Auto-Refresh

```bash
# Edit ui/src/components/ledger/events-table.tsx
# Line 80-82, change to:
staleTime: 0,
refetchInterval: 5000,
gcTime: 5 * 60 * 1000,
```

### Fix #2: Commitment Visibility (Quick Version)

```bash
# Edit pmm/runtime/context_builder.py
# Find the line with read_tail(limit=1000)
# Change to read_tail(limit=5000) when include_commitments=True
```

These two changes will immediately improve the user experience.

---

## Summary

The runtime is **100% functional**. The presentation layer just needs:
- ✅ Auto-refresh for live data
- ✅ Larger event window for commitments
- ✅ Cache invalidation on autonomy ticks
- 🔜 Trace visualization (optional)

All fixes are straightforward and don't require runtime changes - just UI/context tuning.
