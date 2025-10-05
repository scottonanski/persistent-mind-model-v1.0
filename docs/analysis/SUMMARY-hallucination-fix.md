# Hallucination Detector False Positives - Fix Summary

**Date:** 2025-10-02  
**Status:** ✅ **FIXED**  
**Files Modified:** 2  
**Tests Added:** 15  
**All Tests:** ✅ Passing (67/67 parser tests, all commitment tests passing)

## What Was the Problem?

The hallucination detector was generating **false positives** when smaller models (like IBM granite4:latest 1.9GB) referenced past events. The events existed in the ledger, but the extraction logic was too broad and caught narrative descriptions instead of actual commitment claims.

### Example False Positive

**Model said:**
> "the most recent reflection (event #1048 on 2025‑10‑02 21:03) flagged a low openness score"

**Detector flagged:**
> ⚠️ Commitment hallucination detected

**Reality:**
- Event #1048 EXISTS in the ledger (kind: `reflection`)
- Model was describing a past event, not claiming a new commitment
- This was a **false positive**

## Root Causes Found

1. **Overly broad pattern matching** - "focused on X" caught narrative text
2. **No first-person checking** - Extracted third-person descriptions
3. **No example filtering** - Caught "such as X", "for example Y"
4. **Markdown artifacts** - Extracted `**` symbols in text

## What Was Fixed

### 1. Added Example Filtering
```python
# Skip sentences with example indicators
example_markers = ["such as", "for example", "e.g.", "like ", "imagine", "consider"]
if any(marker in sent_lower for marker in example_markers):
    continue
```

### 2. Added First-Person Requirement
```python
# Only extract if sentence has first-person indicators
first_person = ["i ", "my ", "i'm ", "i've ", "i'll "]
if any(fp in sent_lower for fp in first_person):
    # Extract commitment claim
```

### 3. Removed Overly Broad Pattern
```python
# Pattern: "focused on X" - REMOVED (too broad, catches narrative)
```

### 4. Added Markdown Symbol Filtering
```python
def _extract_until_punctuation(text: str) -> str:
    """Extract text until punctuation, quote, or markdown symbol."""
    for char in text:
        if char in ".,;!?\"'*_`":  # Added markdown symbols
            break
```

## Files Modified

### `/pmm/utils/parsers.py`
- **Function:** `extract_commitment_claims()` (lines 360-468)
- **Changes:**
  - Added example marker filtering
  - Added first-person requirement for "committed to" pattern
  - Added first-person requirement for "opened commitment" pattern
  - Removed "focused on" pattern (too broad)
  - Updated `_extract_until_punctuation()` to stop at markdown symbols

### `/tests/test_parsers.py`
- **Added:** `TestExtractCommitmentClaims` class with 15 tests
- **Tests cover:**
  - Valid first-person claims (should extract)
  - Narrative descriptions (should NOT extract)
  - Examples with "such as" (should NOT extract)
  - Third-person descriptions (should NOT extract)
  - Markdown formatting (should filter)
  - Real-world false positives from granite4 chat logs

## Test Results

```bash
# All parser tests pass
$ python -m pytest tests/test_parsers.py -v
67 passed in 0.07s ✅

# All commitment tests pass
$ python -m pytest tests/ -k "commitment" -q
114 passed ✅
```

## Verification with Real Data

Checked the actual database from the chat session:

```bash
$ sqlite3 .data/pmm.db "SELECT id, kind FROM events WHERE id IN (1048, 1050, 1294, 1367, 1455);"

1048|reflection          ✅ EXISTS
1050|commitment_open     ✅ EXISTS
1294|reflection          ✅ EXISTS
1367|reflection_action   ✅ EXISTS
1455|reflection          ✅ EXISTS
```

**Conclusion:** All events the model referenced were real. The detector was incorrectly flagging valid references.

## Impact

### Before Fix
- ❌ False positives on narrative descriptions
- ❌ False positives on examples ("such as X")
- ❌ False positives on past event references
- ❌ Extracted markdown artifacts
- ❌ Poor experience with smaller models

### After Fix
- ✅ Only extracts first-person commitment claims
- ✅ Filters out examples and hypotheticals
- ✅ Ignores narrative descriptions
- ✅ Stops at markdown symbols
- ✅ Better experience with smaller models

## Testing with Smaller Models

The fixes specifically help smaller models like:
- IBM granite4:latest (1.9GB)
- llama3.2:1b
- deepseek-r1:1.5b
- gemma3:1b

These models tend to:
- Use more narrative language
- Reference past events for context
- Give examples in explanations
- Be more verbose

The improved extraction logic now correctly distinguishes between:
- **Active claims:** "I committed to X" → Extract ✅
- **Past references:** "Event #1048 suggested X" → Ignore ✅
- **Examples:** "such as X" → Ignore ✅
- **Narrative:** "The system focused on Y" → Ignore ✅

## Remaining Work

### Short-term (Optional)
- Monitor false positive rate in production
- Consider adding confidence scoring

### Long-term (Future Enhancement)
- Semantic analysis using LLM to classify statement types
- Separate validators for new claims vs past references
- Add tense checking (present/past vs future/conditional)

## How to Use

The fixes are automatic - no code changes needed in calling code. The hallucination detector in `pmm/runtime/loop.py` already uses `extract_commitment_claims()` from `pmm/utils/parsers.py`.

### To Test Manually
```python
from pmm.utils.parsers import extract_commitment_claims

# Valid claim - extracts
text = "I committed to improving openness"
print(extract_commitment_claims(text))
# Output: ['improving openness']

# Narrative - ignores
text = "Event #1048 suggested improving openness"
print(extract_commitment_claims(text))
# Output: []

# Example - ignores
text = "such as increasing openness by 0.02"
print(extract_commitment_claims(text))
# Output: []
```

## Related Documents

- **Full Analysis:** `/docs/analysis/hallucination-detector-false-positives.md`
- **Code:** `/pmm/utils/parsers.py` (line 360-468)
- **Tests:** `/tests/test_parsers.py` (line 280-368)

## Conclusion

The "hallucinations" reported in the granite4 chat logs were actually **false positives from the hallucination detector**. The events existed in the ledger, but the extraction logic was too aggressive.

The fixes make the detector more precise by:
1. Requiring first-person indicators for commitment claims
2. Filtering out examples and hypotheticals
3. Removing overly broad patterns
4. Handling markdown formatting correctly

This improves the user experience, especially with smaller models that use more narrative language.

**Status:** ✅ **COMPLETE** - All tests passing, ready for production use.
