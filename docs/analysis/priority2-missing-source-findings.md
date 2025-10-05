# Priority 2: Missing Source Metadata - Root Cause Found

**Date**: 2025-10-02  
**Status**: Root cause identified

---

## Problem Statement

All 63 `commitment_open` events in the ledger show:
- **NO `source` field** in metadata
- Instead have: `reason="reflection"`, `ref`, `due`
- Cannot distinguish user vs assistant commitments

---

## Root Cause: Direct EventLog Writes Bypassing Tracker

### The Issue

There are **TWO code paths** creating commitments directly via `eventlog.append()` instead of using `tracker.add_commitment()`:

#### Path 1: `Runtime.reflect()` (line 3079-3089)
```python
self.eventlog.append(
    kind="commitment_open",
    content=f"Commitment opened: {snippet}",
    meta={
        "cid": _uuid.uuid4().hex,
        "reason": "reflection",  # <-- NOT "source"
        "text": ref_text,        # <-- FULL reflection text!
        "ref": last_ref.get("id"),
        "due": _compute_reflection_due_epoch(),
    },
)
```

#### Path 2: `emit_reflection()` (line 4113-4117)
```python
eventlog.append(
    kind="commitment_open",
    content=f"Commitment opened: {snippet}",
    meta=open_meta,  # Contains "reason" not "source"
)
```

### Why This is Wrong

1. **Bypasses `tracker.add_commitment()`** which:
   - Sets `source` field correctly
   - Handles deduplication
   - Manages project grouping
   - Validates commitment text

2. **Uses `reason` instead of `source`**:
   - `reason="reflection"` is semantically different from `source="reflection"`
   - Breaks source attribution tracking
   - Inconsistent with commitments from `_extract_commitments_from_text()`

3. **Takes FULL reflection text** (line 3075, 4097):
   ```python
   ref_text = (last_ref.get("content") or "").strip()
   # ...
   "text": ref_text,  # Could be 1000+ characters!
   ```
   - This is the SAME bug we just fixed in Priority 1!
   - Reflection text should NOT become commitment text

---

## Evidence from Ledger

```python
Event 3300:
  Source: NOT_FOUND
  Text: "Event ID 001, CID abcdef... IAS is already at maximum (1.000)..."
  All meta keys: ['cid', 'reason', 'text', 'ref', 'due']
  # Missing: 'source'
  # Has: 'reason' = 'reflection'
```

All 63 commitments follow this pattern:
- Created by direct `eventlog.append()` calls
- Have `reason="reflection"`
- Contain full reflection text
- Missing `source` field

---

## The Correct Path (Already Exists!)

The `_extract_commitments_from_text()` method DOES use the tracker correctly:

```python
tracker.add_commitment(
    normalized,
    source=speaker,  # ✅ Sets source correctly
    extra_meta={
        "source_event_id": int(source_event_id),
        "semantic_score": round(float(score), 3),
        "original_text": commit_text,
    },
)
```

And `tracker.add_commitment()` preserves it:

```python
meta: dict = {"cid": cid, "text": text}
if source is not None:
    meta["source"] = source  # ✅ Adds source to metadata
# ...
self.eventlog.append(kind="commitment_open", content=content, meta=meta)
```

---

## Why These Direct Writes Exist

Looking at the code context, these appear to be **legacy code** from before the commitment tracker was fully implemented. They're trying to:

1. Create commitments directly from reflections
2. Track them with `reason="reflection"` for special handling
3. Set a `due` date for reflection-sourced commitments

But they're doing it **incorrectly** by bypassing the tracker.

---

## Impact

### Current State
- ❌ All commitments missing `source` field
- ❌ Full reflection text used as commitment text
- ❌ No deduplication (bypasses tracker logic)
- ❌ Inconsistent metadata structure
- ❌ Cannot track user vs assistant vs reflection commitments

### After Fix
- ✅ All commitments have `source` field
- ✅ Only actionable text becomes commitments
- ✅ Deduplication works correctly
- ✅ Consistent metadata structure
- ✅ Can track commitment attribution

---

## Recommended Fix

### Option 1: Use Tracker (Preferred)

Replace direct `eventlog.append()` calls with `tracker.add_commitment()`:

```python
# BEFORE (line 3079-3089)
self.eventlog.append(
    kind="commitment_open",
    meta={"cid": ..., "reason": "reflection", "text": ref_text, ...}
)

# AFTER
tracker.add_commitment(
    text=action_text,  # NOT full reflection!
    source="reflection",
    extra_meta={
        "reflection_id": last_ref.get("id"),
        "due": _compute_reflection_due_epoch(),
    }
)
```

### Option 2: Add Source to Direct Writes (Minimal)

If we must keep direct writes, replace `reason` with `source`:

```python
meta={
    "cid": _uuid.uuid4().hex,
    "source": "reflection",  # ✅ Use source, not reason
    "text": action_text,      # NOT full reflection!
    "ref": last_ref.get("id"),
    "due": _compute_reflection_due_epoch(),
}
```

**Note**: No backward compatibility needed - this is active development with fresh DBs.

---

## Related to Priority 1

This is actually **the same bug** we fixed in Priority 1, but in a different location:

| Priority | Issue | Location | Status |
|----------|-------|----------|--------|
| **P1** | Reflection text extracted as commitment | `_extract_commitments_from_text()` | ✅ FIXED |
| **P2** | Reflection text directly written as commitment | `reflect()` / `emit_reflection()` | ⏳ TODO |

Both were creating commitments from full reflection text instead of extracting actionable statements.

---

## Next Steps

1. **Decide on fix approach** (Option 1 vs Option 2)
2. **Extract action text** from reflections instead of using full text
3. **Use tracker** or add `source` field
4. **Update tests** to verify source metadata
5. **Verify** new commitments have `source` field

---

## Questions for Scott

1. Should reflection-sourced commitments use `tracker.add_commitment()` or keep direct writes?
2. If keeping direct writes, should we add both `source` and `reason` fields?
3. How should we extract actionable text from reflections for commitment creation?

