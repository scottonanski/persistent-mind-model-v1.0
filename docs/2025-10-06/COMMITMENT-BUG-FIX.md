# Commitment Visibility Bug - Root Cause and Fix

## The Bug

When asked "What commitments do you have?", the LLM showed **expired commitments** instead of currently open ones.

**Symptoms**:
- LLM listed commitments with IDs 38, 64, 221 (all expired)
- Did not show current open commitments (IDs 1611, 1641)
- Hallucination detector triggered false positives

## Root Cause

**File**: `pmm/runtime/context_builder.py:246`

**Buggy Code**:
```python
for ev in reversed(events):
    if ev.get("kind") == "commitment_close":  # ← Only checks close, not expire!
        cid = (ev.get("meta") or {}).get("cid")
        if cid:
            closed_cids.add(cid)
```

**Issue**: The code only checked for `commitment_close` events but **ignored `commitment_expire` events**.

This meant:
- Commitments that were explicitly closed → filtered out ✅
- Commitments that expired due to timeout → **still shown as open** ❌

## The Fix

**Changed line 246**:
```python
if ev.get("kind") in ("commitment_close", "commitment_expire"):
```

Now the code correctly filters out both closed AND expired commitments.

## Diagnostic Process

### Step 1: Added Debug Logging

Added context preview logging to `.logs/context_preview.txt` to see what the LLM actually receives.

### Step 2: Inspected Context

```bash
cat .logs/context_preview.txt
```

**Found**:
```
Open commitments:
  - [38:b2333220] Why-mechanics: This change raises...
  - [64:214444ea] Reflection: focusing on one concrete next-step
  - [221:45818ed4] 3. Monitor IAS/GAS after implementation...
```

**Problem**: These commitments were expired (IDs 355, 356, 460), not current.

### Step 3: Checked Ledger

```sql
SELECT id, kind, meta FROM events 
WHERE kind IN ('commitment_open', 'commitment_expire') 
ORDER BY id;
```

**Result**:
- ID 38 opened, expired at ID 355
- ID 64 opened, expired at ID 356
- ID 221 opened, expired at ID 460
- ID 1611 opened (still open)
- ID 1641 opened (still open)

### Step 4: Found Bug

The context builder wasn't filtering out expired commitments.

## Testing

**Before Fix**:
```
"What commitments do you have?"
→ Shows 3 expired commitments (38, 64, 221)
→ Hallucination detector triggers
```

**After Fix** (expected):
```
"What commitments do you have?"
→ Shows 2 current commitments (1611, 1641)
→ No hallucination warnings
```

## Impact

This bug affected:
- **Commitment visibility** - LLM saw stale data
- **Hallucination detection** - False positives triggered
- **User trust** - System appeared to be confused about its own state

## Related Issues Fixed

1. ✅ **Autonomy loop** - Now running (48 ticks)
2. ✅ **IO helpers** - Standardized event emission
3. ✅ **Ledger auto-refresh** - UI updates every 5s
4. ✅ **Commitment inclusion** - Always in context (`include_commitments=True`)
5. ✅ **Commitment filtering** - Now filters expired commitments

## Files Modified

1. `pmm/runtime/context_builder.py` - Fixed commitment filtering
2. `pmm/runtime/loop/pipeline.py` - Added debug logging
3. `pmm/runtime/loop/pipeline.py` - Set `include_commitments=True`

## Verification

**Restart server and test**:
```bash
./start-companion.sh
```

**Send message**:
```
"What commitments do you have? List them with event IDs."
```

**Expected response**:
```
I have 2 open commitments:

1. [1611:67a63179] Policy update: Set policy.novelty_threshold = 0.45.

2. [1641:67bfb9a8] IAS is fully aligned (1.000), but GAS is below target (0.552)...
```

## Summary

**Root Cause**: Context builder only checked `commitment_close`, not `commitment_expire`  
**Fix**: Changed to check both event types  
**Impact**: LLM now sees accurate, current commitment state  
**Status**: ✅ Fixed, ready for testing
