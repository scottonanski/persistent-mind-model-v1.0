# Performance Analysis Summary - 2025-10-04

## Problem Statement

After the massive refactor of `loop.py` (6,701 → 4,595 LOC) and `tracker.py` (~1,200 LOC), **performance is now worse than before**.

## Root Cause Identified

**Excessive `read_all()` calls**: 134 total calls found across the codebase.

### Critical Bottlenecks

| Function | read_all() Calls | Impact |
|----------|------------------|--------|
| `AutonomyLoop.tick()` | **17** | Every 10 seconds |
| `handle_identity_adopt()` | **10** | Per identity change |
| `emit_reflection()` | **5** | Per reflection |
| `maybe_reflect()` | **5** | Per reflection check |
| `_rebind_commitments_on_identity_adopt()` | **6** | Per identity rebind |

**Total in hot paths**: ~43 calls per autonomy tick (when reflection triggers)

## Why This Happened

The refactor extracted functions into separate modules. Each extracted function now independently calls `read_all()` instead of receiving events as parameters.

**Before** (monolithic):
```python
def tick(self):
    events = self.eventlog.read_all()  # Once
    self._do_something(events)
    self._do_another_thing(events)
```

**After** (modular):
```python
def tick(self):
    self._do_something()  # Calls read_all() internally
    self._do_another_thing()  # Calls read_all() internally
```

## Performance Impact

With 1,000 events:
- `read_all()` cost: ~5ms
- Tick overhead: 43 × 5ms = **215ms per tick**

With 10,000 events:
- `read_all()` cost: ~50ms
- Tick overhead: 43 × 50ms = **2,150ms (2.15 seconds) per tick**

**This explains the performance degradation.**

## Solution

### Phase 1: Pass Events as Parameters (1-2 hours, 80% improvement)

Modify top-level functions to call `read_all()` once and pass events to helpers:

```python
def tick(self):
    events = self.eventlog.read_all()  # Once
    self._do_something(events)
    self._do_another_thing(events)
```

**Expected reduction**: 134 calls → ~30 calls (77% reduction)

### Phase 2: Request-Scoped Caching (2-4 hours, additional 50% improvement)

Implement a cache that persists for the duration of a single operation:

```python
cache = EventCache(self.eventlog)
events = cache.get_events()  # First call: reads from DB
# ... all subsequent calls use cache ...
```

**Expected reduction**: ~30 calls → ~5 calls (83% further reduction)

**Total improvement**: 5-10× faster

## Tools Created

1. **`scripts/analyze_read_all_hotspots.py`** - Static analysis of read_all() calls
2. **`scripts/profile_performance.py`** - Runtime performance profiling
3. **`docs/PERFORMANCE-BOTTLENECKS-2025-10-04.md`** - Detailed analysis (14 pages)
4. **`docs/PERFORMANCE-FIX-QUICKSTART.md`** - Implementation guide (8 pages)

## Quick Start

### 1. Diagnose the Problem

```bash
python3 scripts/analyze_read_all_hotspots.py
```

### 2. Review the Analysis

```bash
cat docs/PERFORMANCE-BOTTLENECKS-2025-10-04.md
```

### 3. Implement Phase 1 Fixes

```bash
cat docs/PERFORMANCE-FIX-QUICKSTART.md
```

Focus on:
- `AutonomyLoop.tick()` (17 calls → 1 call)
- `handle_identity_adopt()` (10 calls → 1 call)
- Reflection functions (10 calls → 0 calls)

### 4. Validate

```bash
# Before
python3 scripts/analyze_read_all_hotspots.py > before.txt

# After fixes
python3 scripts/analyze_read_all_hotspots.py > after.txt

# Compare
diff before.txt after.txt

# Run tests
pytest -q
```

## Expected Results

| Metric | Before | After Phase 1 | After Phase 2 |
|--------|--------|---------------|---------------|
| read_all() calls/tick | 43 | 5-8 | 1 |
| Tick overhead (1K events) | 215ms | 25-40ms | 5-10ms |
| Tick overhead (10K events) | 2,150ms | 250-400ms | 50-100ms |
| Improvement | - | 5-8× | 20-40× |

## Risk Assessment

**Low Risk** (Phase 1):
- Pure refactor, no behavior change
- Backward compatible (optional parameters)
- Easy to rollback

**Medium Risk** (Phase 2):
- Cache invalidation must be correct
- Requires careful testing

## Success Criteria

- [ ] read_all() calls reduced by >80%
- [ ] Autonomy tick overhead <50ms (1K events)
- [ ] All tests passing (707 passed, 4 skipped)
- [ ] No behavior changes (deterministic replay preserved)

## Next Steps

1. **Review** this summary and detailed docs
2. **Implement** Phase 1 fixes (start with `tick()`)
3. **Validate** with tests and profiler
4. **Measure** improvement
5. **Proceed** to Phase 2 if needed

## Files to Review

1. **Analysis**: `docs/PERFORMANCE-BOTTLENECKS-2025-10-04.md`
2. **Quick Start**: `docs/PERFORMANCE-FIX-QUICKSTART.md`
3. **Profiler**: `scripts/profile_performance.py`
4. **Analyzer**: `scripts/analyze_read_all_hotspots.py`

## Key Insight

**The refactor itself is not the problem.** The code organization is better. The issue is that we inadvertently duplicated database reads when extracting functions. This is a **straightforward fix** with **high impact**.

---

**Status**: Analysis complete, ready for implementation.

**Estimated effort**: 3-6 hours for full fix (Phase 1 + Phase 2)

**Expected improvement**: 5-10× faster performance
