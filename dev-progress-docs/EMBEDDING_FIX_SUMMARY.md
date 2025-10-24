# OpenAI Embedding API Fix Summary

## Problem
When selecting an OpenAI model, the application would hang during initialization with repeated embedding API calls:
```
[openai] POST https://api.openai.com/v1/embeddings model=text-embedding-3-small n_inputs=1 timeout=20.0s retries=2
[openai] POST https://api.openai.com/v1/embeddings model=text-embedding-3-small n_inputs=1 timeout=20.0s retries=2
...
```

The initialization would eventually require a keyboard interrupt (Ctrl+C).

## Root Cause
The `SemanticTraitDriftManager._initialize_embeddings()` method was making **individual API calls** for each exemplar string (33 total), resulting in:
- 8+ sequential API requests during initialization
- Slow startup time
- Potential for timeouts and hangs
- Inefficient use of the OpenAI API

Additionally, the code had a type mismatch: `embed()` returns `list[list[float]]` but was being used as if it returned `list[float]`.

## Solution
Modified `pmm/personality/self_evolution.py` to:

1. **Batch all exemplars into a single API call** in `_initialize_embeddings()`:
   - Collect all 33 exemplar texts into one list
   - Make a single `embed()` call with all texts
   - Reorganize the returned embeddings by trait/direction

2. **Fix type handling** in `apply_event_effects()`:
   - Changed `embed(content)` to `embed([content])[0]`
   - Properly extracts single embedding from the returned list

## Results
**Before:**
- 8+ individual API calls (n_inputs=1 each)
- Hung during initialization
- Required keyboard interrupt

**After:**
- 1 single batch API call (n_inputs=33)
- Completes in ~1.6 seconds
- No hangs or timeouts

## Testing
Verified with test script showing:
```
✓ Total exemplars to embed: 33
🔄 Initializing SemanticTraitDriftManager...
[openai] POST https://api.openai.com/v1/embeddings model=text-embedding-3-small n_inputs=33 timeout=20.0s retries=2
✓ Initialization successful in 1.63s
✓ Exemplar embeddings loaded for 5 traits
```

## Files Modified
- `pmm/personality/self_evolution.py`:
  - `_initialize_embeddings()`: Implemented batch processing
  - `apply_event_effects()`: Fixed embedding extraction

## API Key
The API key in `.env` was correctly configured. The issue was purely about inefficient API usage patterns, not authentication.
