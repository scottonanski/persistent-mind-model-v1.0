# CRITICAL Performance Issue - Still Reading Full History

**Date**: 2025-10-04  
**Status**: 🔴 **URGENT - Major bottleneck identified**

## The Problem

Even with all our cache optimizations, **we're still reading the entire event history** in many places when we only need **recent events (last 500-1000)**.

### Original Optimization (That Made It Fast)

From `docs/performance_optimizations.md`:

> **Context Optimization**: Uses `read_tail(limit=1000)` instead of `read_all()`
> - **Speedup**: 5-10× for large databases
> - **Impact**: Faster context building on every user message

### What's Happening Now

1. **tick()** - Reads ALL events at start (line 2639)
2. **handle_identity_adopt()** - Reads ALL events (line 2145)
3. **Reflection functions** - Read ALL events multiple times
4. **Most operations** - Use full history when they only need recent

### Why This Is Slow

With a growing database:
- 1,000 events: `read_all()` = 5ms, `read_tail(1000)` = 5ms (same)
- 10,000 events: `read_all()` = 50ms, `read_tail(1000)` = 5ms (**10× faster**)
- 100,000 events: `read_all()` = 500ms, `read_tail(1000)` = 5ms (**100× faster**)

**As the database grows, performance degrades linearly!**

## The Fix

### Strategy 1: Use read_tail() for Recent Operations

Most operations only need recent context:
- Reflections: Last 500-1000 events
- Trait updates: Last 500 events
- Commitment checks: Last 1000 events
- Identity checks: Last 500 events

**Only use `read_all()` when you need**:
- Full projection rebuild
- Historical analysis
- Complete commitment history

### Strategy 2: Snapshot Already Has Events

The `_get_snapshot()` method already caches events. Use `snapshot.events` instead of calling `read_all()` again!

```python
# ❌ BAD - Reads all events again
def tick(self):
    snapshot = self._get_snapshot()
    events = self.eventlog.read_all()  # Duplicate read!

# ✅ GOOD - Reuses snapshot events
def tick(self):
    snapshot = self._get_snapshot()
    events = snapshot.events  # Already cached!
```

## Immediate Fixes Needed

### Fix 1: tick() Should Use Snapshot Events

**File**: `pmm/runtime/loop.py` line 2639

**Current**:
```python
def tick(self) -> None:
    from pmm.runtime.request_cache import RequestCache
    _event_cache = RequestCache(self.eventlog)
    
    snapshot_tick = self._snapshot_for_tick()
    events = list(snapshot_tick.events)  # ✅ Good!
```

**But then later** (line 3996, 4005, etc.):
```python
events = _event_cache.get_events()  # ❌ Reads ALL events!
```

**Should be**:
```python
# Use snapshot events throughout, or read_tail for recent checks
events = snapshot_tick.events  # Already have them!
```

### Fix 2: Reflection Functions Should Use read_tail

**File**: `pmm/runtime/loop/reflection.py`

**Current** (lines 164, 195, 224, 257, 351):
```python
events = eventlog.read_all()  # ❌ Reads entire history
```

**Should be**:
```python
# For recent context (most reflections)
events = eventlog.read_tail(limit=1000)  # ✅ 10-100× faster

# Or use passed events if available
if events is None:
    events = eventlog.read_tail(limit=1000)
```

### Fix 3: handle_identity_adopt Should Use read_tail

**File**: `pmm/runtime/loop.py` line 2145

**Current**:
```python
events_before = _event_cache.get_events()  # Reads ALL
```

**Should be**:
```python
# Identity is in recent events
events_before = self.eventlog.read_tail(limit=500)  # Much faster
```

## Performance Impact

### Current State (With Caches But Full Reads)
- 10K events: ~50ms per read_all() × 10 calls = **500ms overhead**
- 100K events: ~500ms per read_all() × 10 calls = **5000ms (5 seconds) overhead**

### After read_tail Optimization
- 10K events: ~5ms per read_tail(1000) × 10 calls = **50ms overhead** (10× faster)
- 100K events: ~5ms per read_tail(1000) × 10 calls = **50ms overhead** (100× faster)

## Why This Wasn't Caught

1. **Small test databases** - With <1000 events, `read_all()` and `read_tail()` perform similarly
2. **Cache focus** - We focused on eliminating redundant reads, not optimizing each read
3. **Snapshot events** - We have the events in the snapshot but keep calling `read_all()` anyway

## Action Plan

### Priority 1: Use Snapshot Events (5 minutes)
- tick() already has `snapshot_tick.events`
- Stop calling `_event_cache.get_events()` and use `snapshot_tick.events`

### Priority 2: read_tail in Reflections (15 minutes)
- Replace `eventlog.read_all()` with `eventlog.read_tail(limit=1000)` in reflection.py
- Most reflection context is in recent 1000 events

### Priority 3: read_tail in Identity Operations (10 minutes)
- handle_identity_adopt only needs recent events
- Identity changes are in last 500 events

## Expected Results

After these fixes:
- **10× faster** with 10K events
- **100× faster** with 100K events
- **Consistent performance** as database grows

---

**This is the missing piece!** We optimized redundant reads but forgot to optimize WHAT we're reading. We're reading the entire history when we only need recent events!
