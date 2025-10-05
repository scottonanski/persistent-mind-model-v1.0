# User Identity Tracking

**Date:** 2025-10-02  
**Status:** ✅ Implemented  
**Feature:** Track and remember user's name across sessions

## Problem

PMM tracked the assistant's identity but not the user's identity. When a user said "My name is Scott," PMM would:
- ❌ Not log it to the ledger
- ❌ Not remember it in future sessions
- ❌ Not inject it into context for the LLM

## Solution

Implemented user identity tracking with three components:

### 1. Intent Classification
**File:** `pmm/directives/classifier.py`

Added `user_self_identification` intent detection for patterns:
- "I'm [name]"
- "I am [name]"
- "My name is [name]"
- "My name's [name]"
- "Call me [name]"

```python
if any(pattern in f" {text_lower} " for pattern in user_intro_patterns):
    return "user_self_identification", candidate, 0.9
```

### 2. Ledger Logging
**File:** `pmm/runtime/loop.py`

When user self-identification is detected, log a `user_identity_set` event:

```python
if intent == "user_self_identification" and candidate_name:
    self.eventlog.append(
        kind="user_identity_set",
        content=f"User identified as: {candidate_name}",
        meta={
            "user_name": candidate_name,
            "confidence": float(confidence),
            "source": "user_input",
        },
    )
```

### 3. Context Injection
**File:** `pmm/runtime/context_builder.py`

Retrieve user name from ledger and inject into system context:

```python
# Retrieve user name from most recent user_identity_set event
for ev in reversed(events):
    if ev.get("kind") == "user_identity_set":
        user_name = ev.get("meta", {}).get("user_name")
        break

# Inject into context
lines.append(f"User: {user_name}")
```

## How It Works

### Example Flow

```
User: "My name is Scott"
  ↓
Classifier detects: user_self_identification, name="Scott", confidence=0.9
  ↓
Runtime logs: user_identity_set event with meta.user_name="Scott"
  ↓
Context builder retrieves: user_name="Scott" from ledger
  ↓
System prompt includes: "User: Scott"
  ↓
Next session: LLM knows user is Scott
```

### Ledger Event

```json
{
  "id": 1542,
  "kind": "user_identity_set",
  "content": "User identified as: Scott",
  "meta": {
    "user_name": "Scott",
    "confidence": 0.9,
    "source": "user_input"
  }
}
```

### Context Output

```
[SYSTEM STATE — from ledger]
Identity: Persistent Mind Model Alpha
User: Scott
Traits: O=0.50, C=0.46, E=0.50, A=0.50, N=0.50
...
```

## Test Coverage

**File:** `tests/test_naming.py`

Added 3 new tests:
1. `test_user_self_identification_logged` - Verifies event is logged
2. `test_user_name_persists_across_context` - Verifies name appears in context
3. `test_multiple_user_names_uses_latest` - Verifies latest name is used

All 11 naming tests pass ✅

## Behavior

### User Self-Identification
```
User: "I'm Scott"
→ Logs user_identity_set event
→ Does NOT adopt "Scott" as assistant name
```

### Assistant Naming
```
User: "Your name is Echo"
→ Logs name_attempt_user event
→ May adopt "Echo" as assistant name (via autonomy loop)
```

### Persistence
- User name persists across sessions
- Most recent name is used if user changes it
- Name is deterministically retrieved from ledger

## Benefits

✅ **User Recognition** - PMM remembers who you are  
✅ **Persistent State** - Name stored in immutable ledger  
✅ **Context Aware** - LLM has access to user identity  
✅ **Deterministic** - Same ledger → same user name  
✅ **Auditable** - All name changes logged with timestamps  

## Future Enhancements

Potential additions:
- User preferences tracking
- User conversation history
- Multi-user support (track multiple users)
- User role/relationship tracking

## Related

- **Identity System:** `pmm/directives/classifier.py`
- **Context Builder:** `pmm/runtime/context_builder.py`
- **Runtime Loop:** `pmm/runtime/loop.py`
- **Tests:** `tests/test_naming.py`
