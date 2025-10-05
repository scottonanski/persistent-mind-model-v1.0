# Hallucination Detector False Positives Analysis

**Date:** 2025-10-02  
**Model Tested:** IBM granite4:latest (1.9GB) on i10700k, 32GB RAM, RTX 3080  
**Issue:** Hallucination detector flagging valid references as hallucinations

## Executive Summary

The hallucination detector in `pmm/runtime/loop.py` is generating **false positives** when smaller models reference past events. The events exist in the ledger, but the commitment claim extraction logic in `pmm/utils/parsers.py` is too broad and extracts narrative descriptions rather than actual commitment claims.

## Evidence

### Test Session Details
- **Database:** Fresh `.data/pmm.db` 
- **Total Events:** 2,358
- **Open Commitments:** 15
- **Model:** granite4:latest (1.9GB local model)

### Example False Positive #1

**Model Response:**
```
the most recent reflection (event #1048 on 2025‑10‑02 21:03) flagged a low "openness" 
score and suggested an adjustment to the **novelty‑threshold policy knob**
```

**Detector Warning:**
```
⚠️ Commitment hallucination detected: LLM claimed commitment about 
'** the most recent reflection (event #1048 on 2025‑10‑02 21:03) flagged a low "openness" 
score and suggested an adjustment to the **novelty‑threshold policy knob**' 
but no matching commitment_open found in ledger.
```

**Reality:**
- Event #1048 EXISTS (kind: `reflection`)
- Event #1050 EXISTS (kind: `commitment_open`, CID: `1b7d01b17a3148e3b701d72471d1212b`)
- Event #1050 was CLOSED at event #1206
- Model was **describing** a past reflection, not claiming a new commitment

### Example False Positive #2

**Model Response:**
```
truly serves a meaningful evolution rather than becoming stale habit
```

**Detector Warning:**
```
⚠️ Commitment hallucination detected: LLM claimed commitment about 
'truly serves a meaningful evolution rather than becoming stale habit' 
but no matching commitment_open found in ledger.
```

**Reality:**
- This is narrative text from a philosophical response
- No commitment claim was made
- Detector extracted "focused on" pattern incorrectly

### Example False Positive #3

**Model Response:**
```
such as "increase openness by 0.02"
```

**Detector Warning:**
```
⚠️ Commitment hallucination detected: LLM claimed commitment about 
'such as "increase openness by 0' but no matching commitment_open found in ledger.
```

**Reality:**
- This is an **example** given in response to a question
- Model used "such as" to illustrate, not to claim
- Detector extracted partial text incorrectly

## Root Causes

### 1. Bug in `extract_commitment_claims()` (Line 379)

```python
text.lower()  # ❌ Result not assigned
claims: list[str] = []
```

Should be:
```python
text = text.lower()  # ✅ Assign result
claims: list[str] = []
```

### 2. Overly Broad Pattern Matching

The function catches narrative descriptions, not just commitment claims:

```python
# Pattern: "focused on X" - TOO BROAD
if "focused on" in sent_lower:
    idx = sent_lower.find("focused on")
    rest = sentence[idx + len("focused on") :].strip()
    claim = _extract_until_punctuation(rest)
    if claim:
        claims.append(claim.lower())
```

This catches:
- ✅ "I focused on improving openness" (valid claim)
- ❌ "The system focused on stability" (narrative)
- ❌ "We should focus on growth" (suggestion)

### 3. No Context Awareness

The detector doesn't distinguish between:
- **Active claims**: "I committed to X", "I opened commitment Y"
- **Past references**: "Event #1048 suggested X", "The reflection mentioned Y"
- **Examples**: "such as X", "for example Y"
- **Hypotheticals**: "I could commit to X", "We might focus on Y"

### 4. Extracts Markdown Artifacts

The detector extracts markdown formatting:
```
'** the most recent reflection...**'
```

This happens because `_extract_until_punctuation()` only stops at `.,;!?"'` but not at markdown symbols like `*`.

## Verification Queries

```bash
# Check if events exist
sqlite3 .data/pmm.db "SELECT id, kind FROM events WHERE id IN (1048, 1050, 1294, 1367, 1455);"

# Output:
1048|reflection
1050|commitment_open
1294|reflection
1367|reflection_action
1455|reflection

# Check commitment status
sqlite3 .data/pmm.db "SELECT id, kind, json_extract(meta, '$.cid') FROM events 
WHERE json_extract(meta, '$.cid') = '1b7d01b17a3148e3b701d72471d1212b';"

# Output:
1050|commitment_open|1b7d01b17a3148e3b701d72471d1212b
1206|commitment_close|1b7d01b17a3148e3b701d72471d1212b
```

## Impact on Smaller Models

**Why this affects smaller models more:**

1. **Narrative style**: Smaller models (like granite4:1.9b) tend to be more verbose and narrative
2. **Context references**: They frequently reference past events to build coherence
3. **Example usage**: They use more examples and hypotheticals in explanations
4. **Less precise language**: They may use broader phrases like "focused on" vs "committed to"

**This creates a feedback loop:**
- Model references past events (valid behavior)
- Detector flags as hallucination (false positive)
- User sees "😕 Hmm, that doesn't match the ledger..."
- User loses trust in the model
- Model's actual hallucinations get lost in noise

## Recommendations

### Short-term Fixes

1. **Fix the bug on line 379**
   ```python
   text = text.lower()  # Assign result
   ```

2. **Remove overly broad patterns**
   - Remove "focused on" pattern (too narrative)
   - Make "open commitment" pattern more strict (require first-person)

3. **Add markdown filtering**
   ```python
   def _extract_until_punctuation(text: str) -> str:
       result = []
       for char in text:
           if char in ".,;!?\"'*_`":  # Add markdown symbols
               break
           result.append(char)
       return "".join(result).strip()
   ```

### Medium-term Improvements

1. **Add context checking**
   ```python
   # Only extract if sentence has first-person indicators
   first_person = ["i ", "my ", "i'm ", "i've ", "i'll "]
   if any(fp in sent_lower for fp in first_person):
       # Extract commitment claim
   ```

2. **Add tense checking**
   - Only flag present/past tense claims: "I committed", "I opened"
   - Ignore future/conditional: "I will commit", "I could open"

3. **Add example filtering**
   ```python
   # Skip sentences with example indicators
   example_markers = ["such as", "for example", "e.g.", "like ", "imagine"]
   if any(marker in sent_lower for marker in example_markers):
       continue  # Skip this sentence
   ```

### Long-term Solutions

1. **Semantic analysis**: Use the LLM itself to classify whether a statement is:
   - An active commitment claim
   - A past event reference
   - A hypothetical example
   - Narrative description

2. **Confidence scoring**: Instead of binary detection, score claims by confidence:
   - High confidence: "I committed to X" (first-person, past tense)
   - Medium confidence: "opened commitment X" (passive voice)
   - Low confidence: "focused on X" (ambiguous)

3. **Separate validators**:
   - `validate_new_commitment_claims()` - for NEW commitments being made
   - `validate_event_references()` - for references to PAST events
   - `validate_commitment_status()` - for status claims (open/closed)

## Testing Strategy

### Test Cases Needed

```python
def test_extract_commitment_claims_narrative_vs_claims():
    """Should distinguish narrative from actual claims."""
    
    # Should extract (valid claims)
    assert extract_commitment_claims("I committed to improving openness") == ["improving openness"]
    assert extract_commitment_claims("I opened commitment to review metrics") == ["to review metrics"]
    
    # Should NOT extract (narrative)
    assert extract_commitment_claims("Event #1048 suggested improving openness") == []
    assert extract_commitment_claims("The reflection focused on stability") == []
    
    # Should NOT extract (examples)
    assert extract_commitment_claims("such as increasing openness by 0.02") == []
    assert extract_commitment_claims("for example, commit to daily reviews") == []
    
    # Should NOT extract (hypotheticals)
    assert extract_commitment_claims("I could commit to X") == []
    assert extract_commitment_claims("We might focus on Y") == []
```

### Integration Test

Run the chat CLI with a smaller model and verify:
1. No false positives when model references past events
2. Real hallucinations are still caught
3. User experience is smooth (no spurious warnings)

## Conclusion

The hallucination detector is working as designed but with **overly aggressive extraction logic**. The events referenced by the model exist in the ledger - the detector is misclassifying narrative descriptions as commitment claims.

**Priority:** Medium-High  
**Effort:** Low (short-term fixes) to Medium (long-term improvements)  
**Impact:** High (affects user trust and smaller model usability)

## Related Files

- `/pmm/utils/parsers.py` - Contains `extract_commitment_claims()` (line 360-462)
- `/pmm/runtime/loop.py` - Contains `_verify_commitment_claims()` (line 165-228)
- `/tests/test_parsers.py` - Test suite for parser functions
