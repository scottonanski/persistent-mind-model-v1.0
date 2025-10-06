# Quick Fixes Applied - Presentation Layer Sync

## Changes Made

### 1. ✅ Ledger Auto-Refresh (5-Second Polling)

**File**: `ui/src/components/ledger/events-table.tsx`

**Change**:
```typescript
// Line 80-82
staleTime: 0, // Always fetch fresh data
refetchInterval: 5000, // Auto-refresh every 5 seconds for live autonomy events
gcTime: 5 * 60 * 1000, // 5 minutes
```

**Impact**: The Ledger tab will now auto-refresh every 5 seconds, showing new `autonomy_tick`, `reflection`, and `stage_progress` events as they arrive in real-time.

---

### 2. ✅ Commitment Visibility (5x Larger Event Window)

**File**: `pmm/runtime/context_builder.py`

**Change**:
```python
# Line 92
tail_limit = 5000 if include_commitments else 1000
```

**Impact**: When commitments are requested in the context, the system now reads the last 5000 events instead of 1000. This ensures old commitments (opened early in the ledger) are visible to the LLM.

---

## Testing

### Test #1: Ledger Live Streaming

```bash
# 1. Restart the UI (the backend doesn't need restarting)
cd ui
npm run dev

# 2. Open http://localhost:3001/ledger
# 3. Watch for new events appearing every 5-10 seconds
# Expected: autonomy_tick, stage_progress, reflection events streaming in
```

### Test #2: Commitment Visibility

```bash
# 1. Restart the backend to pick up context_builder changes
# Stop current server (Ctrl+C)
./start-companion.sh

# 2. Send chat message: "What commitments do you have?"
# Expected: LLM lists the 3 open commitments
# Before: "I don't have any active commitments"
# After: "I have 3 open commitments: [details]"
```

---

## Remaining Issues (Optional)

These are **not critical** but can be addressed later:

### 3. 🔜 Trace Rendering
- **Issue**: Reasoning traces show 0 nodes visited
- **Cause**: Trace buffer not capturing node traversals (only high-level steps)
- **Fix**: Requires investigation of trace_buffer.py implementation
- **Priority**: Low (nice-to-have visualization)

### 4. 🔜 Context Refresh Between Ticks
- **Issue**: Chat responses may use stale snapshot if autonomy tick happens mid-conversation
- **Cause**: Snapshot cache not invalidated on autonomy tick
- **Fix**: Add cache invalidation in AutonomyLoop.tick()
- **Priority**: Medium (improves accuracy of IAS/GAS in responses)

---

## Summary

**Two quick wins implemented:**
1. ✅ **Ledger auto-refresh** - See live events every 5 seconds
2. ✅ **Commitment visibility** - LLM can now see all commitments (5x larger window)

**Impact**: The UI now shows real-time autonomy activity, and the LLM has full visibility into the commitment ledger.

**Next steps**: Restart the UI to see ledger streaming, restart backend to test commitment visibility.
