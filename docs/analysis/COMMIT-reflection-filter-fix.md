# Commitment Reflection Filter Fix

**Date**: 2025-10-02  
**Priority**: Critical (P1)  
**Status**: ✅ Implemented and Tested

## Problem Statement

During testing with `granite4:latest`, we discovered that entire reflection responses (1000+ characters) were being extracted as commitments, polluting the commitment ledger with unactionable text.

### Root Cause

The `_extract_commitments_from_text()` method in `pmm/runtime/loop.py` was calling the commitment extractor on LLM responses without filtering out reflection-like content. The extractor uses embedding similarity, which would match phrases within long reflections, causing the **entire reflection text** to be captured as a commitment.

### Evidence from Ledger

```
[3298] reflection (1895 chars)
  Content: Event ID 001, CID abcdef... IAS is already at maximum (1.000)...
  
[3300] commitment_open (same 1895 chars!)
  Content: Commitment opened: Event ID 001, CID abcdef... IAS is already at maximum (1.000)...
```

Result:
- 63 `commitment_open` events in ledger
- All containing long analytical reflections (200-1900 chars)
- 0 currently open commitments (all expired as unactionable)
- Commitment tracking system rendered useless

## Solution Implemented

### Changes to `pmm/runtime/loop.py`

Added two-layer filtering in `_extract_commitments_from_text()` (lines 1202-1229):

#### 1. Reflection Marker Detection
Filter out text containing reflection-specific markers:
```python
reflection_markers = [
    "event id",
    "ias is", "ias=",
    "gas is", "gas=",
    "stage=",
    "stage s0", "stage s1", "stage s2", "stage s3", "stage s4",
    "why-mechanics:",
    "analytical reflection:",
    "proposed intervention:",
    "ocean dimensions",
    "trait scores",
]
if any(marker in text_lower for marker in reflection_markers):
    continue  # Skip this text, don't create commitment
```

#### 2. Length Limit Enforcement
Enforce maximum commitment text length using existing config constant:
```python
if len(commit_text) > MAX_COMMITMENT_CHARS:  # 400 chars
    continue  # Skip long text, likely a reflection
```

### Test Coverage

Created `tests/test_commitment_reflection_filter.py` with 5 tests:

1. ✅ `test_filter_long_reflection_text` - Verifies long reflections are rejected
2. ✅ `test_filter_reflection_markers` - Validates marker detection
3. ✅ `test_allow_short_actionable_commitments` - Ensures valid commitments still work
4. ✅ `test_max_commitment_chars_constant` - Validates config value
5. ✅ `test_filter_prevents_reflection_pollution` - Integration test

All tests pass:
```
tests/test_commitment_reflection_filter.py .....     [100%]
tests/test_commitment_extractor.py ........          [100%]
```

## Impact

### Before Fix
```
Total commitment_open events: 63
Average commitment length: ~800 characters
Currently open commitments: 0
Commitment ledger: Polluted with reflections
```

### After Fix
- ✅ Reflection text blocked from commitment extraction
- ✅ Only short, actionable commitments allowed (≤400 chars)
- ✅ Reflection markers prevent false positives
- ✅ Existing valid commitments still extracted correctly

### Example: What Gets Filtered

**BLOCKED** (contains "IAS=", "GAS=", "Stage S4", length > 400):
```
Event ID 001, CID abcdef1234567890abcdef1234567890abcdef12  
IAS is already at maximum (1.000), GAS is also maximized (1.000). 
The system has reached Stage S4 with optimal trait scores across 
all OCEAN dimensions (O:0.96, C:0.52, E:0.50, A:0.50, N:0.50). 
[... continues for 1895 characters ...]
```

**ALLOWED** (short, actionable, no markers):
```
I will complete the quarterly report tomorrow
I'll adjust the novelty threshold to 0.45
I plan to work on the database optimization
```

## Compliance with CONTRIBUTING.md

✅ **Ledger integrity** - Prevents pollution of commitment events  
✅ **Determinism** - Filtering logic is deterministic (no randomness)  
✅ **No regex** - Uses simple string matching and length checks  
✅ **Test coverage** - 5 new tests, all existing tests pass  
✅ **Minimal changes** - Focused fix, no over-engineering

## Related Issues

This fix addresses one of three issues discovered during ledger inspection:

1. ✅ **Reflection text extraction** - FIXED (this commit)
2. ⏳ **Missing source metadata** - Still needs investigation
3. ⏳ **LLM fabrication** - Requires prompt engineering

See `docs/analysis/ledger-inspection-findings.md` for full analysis.

## Verification Steps

To verify the fix is working:

1. **Run tests**:
   ```bash
   pytest tests/test_commitment_reflection_filter.py -v
   pytest tests/test_commitment_extractor.py -v
   ```

2. **Check new commitments in ledger**:
   ```python
   from pmm.storage.eventlog import EventLog
   evlog = EventLog(".data/pmm.db")
   events = evlog.read_all()
   
   # Check recent commitment_open events
   opens = [e for e in events if e.get("kind") == "commitment_open"]
   for ev in opens[-10:]:
       text = ev.get("meta", {}).get("text", "")
       print(f"Length: {len(text)}, Text: {text[:100]}...")
   ```

3. **Expected behavior**:
   - All new commitments should be ≤400 characters
   - No commitments containing "IAS=", "GAS=", "Event ID", etc.
   - Only actionable commitment statements

## Future Enhancements

Potential improvements (not critical):

1. **Configurable marker list** - Move reflection_markers to config
2. **Logging** - Log when commitments are filtered (for debugging)
3. **Metrics** - Track filter effectiveness (filtered vs accepted ratio)
4. **Stricter patterns** - Add more reflection markers as discovered

## Rollback Plan

If this fix causes issues:

1. Revert changes to `pmm/runtime/loop.py` lines 1202-1229
2. Remove `tests/test_commitment_reflection_filter.py`
3. Previous behavior will resume (but with reflection pollution)

## Sign-off

- **Implementation**: Complete ✅
- **Testing**: 5 new tests, all pass ✅
- **Documentation**: This file ✅
- **Code review**: Ready for review
- **Deployment**: Safe to merge
