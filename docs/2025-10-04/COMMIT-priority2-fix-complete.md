# Priority 2 Fix: Reflection-Sourced Commitments - Complete

**Date**: 2025-10-02  
**Status**: ✅ **FIXED AND TESTED**

---

## Executive Summary

Fixed the second instance of reflection text being used as commitments. Commitments are now created from **extracted action text** via the tracker, with proper `source="reflection"` metadata.

## What Was Fixed

### The Bug (Same as Priority 1, Different Location)

Two code paths were creating commitments directly via `eventlog.append()`:
1. `Runtime.reflect()` (line 3079-3089) 
2. `emit_reflection()` (line 4065-4107)

Both were:
- Using **full reflection text** instead of extracted actions
- Bypassing `tracker.add_commitment()`
- Using `reason="reflection"` instead of `source="reflection"`
- Missing source attribution

### The Solution

**Location 1: `Runtime.reflect()`** (lines 3063-3089)
- **BEFORE**: Created commitment from full reflection text
- **AFTER**: Creates commitment from extracted `action` text via tracker

```python
# Now uses action text, not full reflection
if action:
    tracker.add_commitment(
        text=action,  # Short, actionable statement
        source="reflection",
        extra_meta={
            "reflection_id": int(rid_reflection),
            "due": _compute_reflection_due_epoch(),
        },
    )
```

**Location 2: `emit_reflection()`** (lines 4065-4067)
- **BEFORE**: Created commitment from full reflection text
- **AFTER**: Removed commitment creation entirely (happens in Runtime.reflect())

```python
# NOTE: Commitment creation from reflections now happens in Runtime.reflect()
# where action extraction occurs. This function only emits the reflection event.
# Removed direct commitment_open creation to avoid using full reflection text.
```

---

## Changes Made

### Code Changes

**File**: `pmm/runtime/loop.py`

1. **Lines 3063-3089**: Replaced direct `eventlog.append()` with `tracker.add_commitment()`
   - Uses `action` text instead of `ref_text`
   - Sets `source="reflection"` 
   - Includes `reflection_id` and `due` in metadata

2. **Lines 4065-4067**: Removed direct commitment creation from `emit_reflection()`
   - Added comment explaining new design
   - Commitments now only created where actions are extracted

### Test Updates

**File**: `tests/test_reflection_commitment_due.py`
- Updated to use `tracker.add_commitment()` instead of expecting `emit_reflection()` to create commitments
- Changed `reason="reflection"` to `source="reflection"`

**File**: `tests/test_reflection_commitments.py`
- Updated both tests to reflect new design
- Commitments created via tracker, not directly from `emit_reflection()`
- Empty reflections no longer create commitments (correct behavior)

---

## Test Results

```bash
$ pytest tests/ -k "reflection" -q
101 passed, 584 deselected, 7 warnings

$ pytest tests/ -k "commitment" -q  
122 passed, 563 deselected, 10 warnings
```

All tests pass! ✅

---

## Impact

### Before Fix
```
Reflection: "Event ID 001, IAS=1.000... [1895 chars]"
↓
commitment_open:
  meta: {
    "reason": "reflection",  # Wrong field
    "text": "[full 1895 char reflection]",  # Wrong text
    # Missing "source" field
  }
```

### After Fix
```
Reflection: "IAS is low, I should improve openness..."
↓ Action extraction ↓
Action: "Adjust novelty threshold to 0.45"
↓ Tracker ↓
commitment_open:
  meta: {
    "source": "reflection",  # ✅ Correct field
    "text": "Adjust novelty threshold to 0.45",  # ✅ Short, actionable
    "reflection_id": 123,  # ✅ Links back to reflection
    "due": 1759530000,  # ✅ Has due date
  }
```

---

## Relationship to Priority 1

Both priorities fixed the **same underlying bug** in different locations:

| Priority | Location | Issue | Status |
|----------|----------|-------|--------|
| **P1** | `_extract_commitments_from_text()` | Reflection text extracted as commitment | ✅ FIXED |
| **P2** | `reflect()` / `emit_reflection()` | Reflection text directly written as commitment | ✅ FIXED |

Root cause: Reflection text being used instead of extracted action text for commitments.

---

## Design Clarification

### The Correct Flow

```
1. Reflection generated
   → "System status: IAS=0.5... Proposed: Adjust threshold to 0.45"
   
2. Action extracted
   → "Adjust threshold to 0.45"
   
3. Commitment created from action
   → tracker.add_commitment(text="Adjust threshold to 0.45", source="reflection")
   
4. Policy applied
   → Threshold actually adjusted
   
5. Commitment closed
   → Evidence of completion
```

### Key Principles

1. **Reflections** = Long analytical text for understanding
2. **Actions** = Short extracted insights from reflections  
3. **Commitments** = Promises to execute actions
4. **Policies** = System changes based on actions

Reflections drive growth through action extraction, NOT by becoming commitments themselves.

---

## Compliance Checklist

✅ **Ledger integrity** - Commitments now have proper source attribution  
✅ **Determinism** - Uses tracker for consistent commitment creation  
✅ **No regex** - Simple string operations only  
✅ **Test coverage** - All tests updated and passing  
✅ **Minimal changes** - Focused fix, ~50 lines changed  
✅ **No breaking changes** - Tests updated to match new design  
✅ **Documentation** - Complete analysis and fix docs  

---

## Verification

To verify the fix works with a fresh database:

```bash
# Start chat with fresh DB
rm -f .data/pmm.db
python -m pmm.cli.chat

# After some reflections, check commitments:
python3 << 'EOF'
from pmm.storage.eventlog import EventLog
evlog = EventLog(".data/pmm.db")
events = evlog.read_all()

commits = [e for e in events if e.get("kind") == "commitment_open"]
for c in commits[-5:]:
    meta = c.get("meta", {})
    print(f"Source: {meta.get('source', 'MISSING')}")
    print(f"Text length: {len(meta.get('text', ''))}")
    print(f"Text: {meta.get('text', '')[:80]}...")
    print()
