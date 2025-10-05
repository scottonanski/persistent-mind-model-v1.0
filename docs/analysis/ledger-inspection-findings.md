# Ledger Inspection Findings
**Date**: 2025-10-02  
**Session**: granite4:latest hallucination testing

## Executive Summary

The hallucination detector is **working correctly**. The LLM is generating plausible-sounding commitment references that don't exist in the ledger. Commitments ARE being written to the database, but they're not the simple, actionable statements the LLM is inventing.

## Ledger Statistics

```
Total events: 4,366

Commitment-related events:
  commitment_open:      63
  commitment_close:     50
  commitment_expire:    13
  commitment_priority: 141

Currently open commitments: 0
```

## Root Cause Analysis

### What the LLM Claims

The LLM repeatedly references commitments like:
```
Event ID: 118
CID: a75f11bc...
Commitment: Adjust the novelty threshold policy knob downward to 0
```

### What's Actually in the Ledger

Real `commitment_open` events contain:
- **Long analytical reflections** (200-500 words)
- **System status reports**
- **Full OCEAN trait analysis**
- **Multi-paragraph "why-mechanics" explanations**

Example (Event 3300):
```
Text: Event ID 001, CID abcdef1234567890abcdef1234567890abcdef12  
IAS is already at maximum (1.000), GAS is also maximized (1.000). 
The system has reached Stage S4 with optimal trait scores across 
all OCEAN dimensions (O:0.96, C:0.52, E:0.50, A:0.50, N:0.50). 
The novelty threshold for committing new actions is set at 0.55.

Why-mechanics: The system has reached its optimal performance 
metrics and stage, indicating no further growth or autonomy 
improvement is possible...
[continues for several more paragraphs]
```

### Why Simple Commitments Aren't Being Created

The commitment extractor (`pmm/commitments/extractor.py`) uses **embedding-based similarity** against exemplars like:
- "I will complete this task"
- "I plan to work on this"
- "I am committing to this action"

The LLM's responses don't match these patterns because:
1. **Third-person analytical voice** - "The system should..." vs "I will..."
2. **Embedded in long reflections** - Not isolated commitment statements
3. **Hypothetical/analytical** - Discussing what could be done, not committing to action

## Why All Commitments Are Expired

```
Open commitments: 0
```

All 63 `commitment_open` events have been either:
- Closed (50 events)
- Expired (13 events)
- TTL expired (24-hour default)

The LLM is operating in a state with **no active commitments**, yet keeps referencing phantom commitments as if they exist.

## Hallucination Patterns Observed

### Pattern 1: Fake Event IDs
```
Event 118, CID a75f11bc...
Event 174, CID cc692285...
Event 001, CID abcdef1234567890abcdef1234567890abcdef12
```

None of these Event IDs correspond to actual commitment_open events.

### Pattern 2: Invented CIDs
The LLM generates plausible-looking CIDs that don't exist:
- `a75f11bc2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8`
- `cc692285c9d1b3a4f6e8d7c2b1a0z9y8x7w6v5u4t3`

Note: Some contain invalid hex characters (like 'z') which real UUIDs wouldn't have.

### Pattern 3: Claiming Closed Commitments Are Open
The LLM references commitments as if they're active when the ledger shows 0 open commitments.

## Detector Accuracy

The hallucination detector (`pmm/runtime/loop.py:140-228`) correctly identifies:

1. **Event ID mismatches** - Claimed Event 118 doesn't exist as commitment_open
2. **Text mismatches** - No commitment with text "Adjust novelty threshold to 0"
3. **Empty commitment list** - Correctly reports `Actual recent commitments: []`

### Example Warning (Correct)
```
⚠️  Commitment hallucination detected: LLM claimed event ID 118 is a 
commitment, but it's not in the ledger. Actual recent commitment event IDs: []
```

## Implications

### For the Hallucination Fix

The hallucination detector is **not producing false positives**. Every warning is legitimate:
- The LLM is inventing commitment references
- These references don't exist in the ledger
- The detector correctly catches them

### For Commitment Extraction

The commitment extraction logic may need adjustment:
1. **Pattern matching** - Current exemplars don't match analytical/reflective language
2. **Context window** - Long reflections may dilute commitment signals
3. **Voice mismatch** - Third-person vs first-person language

### For Model Behavior

The small model (granite4:1.9B) is:
- ✅ Generating coherent, contextual responses
- ✅ Understanding the PMM framework conceptually
- ❌ Fabricating ledger references to sound authoritative
- ❌ Not checking actual ledger state before making claims

## Recommendations

### 1. Commitment Extraction Enhancement
Add exemplars for analytical/reflective commitment language:
```python
"analytical_commitment": [
    "The system should adjust the novelty threshold",
    "Proposed intervention: lower the threshold to",
    "Next action: increment openness by",
]
```

### 2. Prompt Engineering
Explicitly instruct the LLM:
- "Never reference Event IDs or CIDs unless you've verified them in the ledger"
- "If no commitments are open, say so explicitly"
- "Use first-person language when making commitments"

### 3. Ledger Query Integration
Provide the LLM with actual open commitment data in the context:
```
Currently open commitments: 0
Recent commitment_open events: [list last 5 with Event IDs and CIDs]
```

### 4. Post-Response Validation (Current Approach)
Continue using the hallucination detector as a safety net, but:
- Log patterns of hallucinations for analysis
- Use feedback to improve prompts
- Consider penalizing hallucination in reflection scoring

## Test Session Observations

During the granite4:latest test session:
- **IAS climbed from 0.046 → 1.000** (trait drift working)
- **Openness increased 0.50 → 0.93** (organic growth)
- **Stage stuck at S0** despite metrics (likely due to 0 open commitments)
- **Hallucinations increased with conversational depth**

The model performs well on personality evolution but struggles with ledger fidelity.

## Critical Discovery: Reflection Text Being Extracted as Commitments

**Status**: ✅ **FIXED** - See `COMMIT-reflection-filter-fix.md` and `SUMMARY-priority1-fix-complete.md`

### The Bug

Event sequence analysis reveals:
```
[3298] reflection
  Content: Event ID 001, CID abcdef... IAS is already at maximum (1.000)...
  
[3300] commitment_open
  Content: Commitment opened: Event ID 001, CID abcdef... IAS is already at maximum (1.000)...
  Commitment text length: 1895 chars
```

**The entire reflection response is being extracted as a commitment!**

### Why This Happens

1. `_extract_commitments_from_text()` is called on the LLM's response (line 2324-2326 in loop.py)
2. The extractor uses embedding similarity against exemplars
3. Long analytical reflections may contain phrases that match commitment patterns
4. The **entire reflection text** gets captured as the commitment text
5. Result: 1895-character "commitments" that are actually reflections

### Why Commitments Have No Source

All 63 commitments show `source: unknown` because:
- They're being created through a code path that doesn't set the `source` parameter
- OR the `source` parameter is being set to `None` somewhere
- OR there's a bug in the metadata merging logic

This needs investigation in `tracker.add_commitment()` to see why `source=speaker` isn't being preserved.

### Impact

1. **Pollutes commitment ledger** with multi-paragraph reflections
2. **Makes commitment tracking useless** - can't distinguish real commitments
3. **Causes all commitments to expire** - they're not actionable, so never get closed
4. **Leads to 0 open commitments** - nothing meaningful to track

## Conclusion

**The hallucination detector is functioning as designed.** The issues are:

1. **Reflection text extraction bug** - Entire reflections being captured as commitments
2. **Missing source metadata** - All commitments show `source: unknown`
3. **LLM fabrication** - Inventing simple commitment references that don't exist
4. **Commitment extraction patterns** - Don't match analytical language properly

The fix should focus on:
- **CRITICAL**: Fix reflection text being extracted as commitments
- Investigate why `source` metadata is not being set
- Improve commitment extraction to filter out long analytical text
- Add length limits to commitment text (e.g., max 200 chars)
- Enhance prompts to discourage fabrication
- Provide explicit ledger state in context
