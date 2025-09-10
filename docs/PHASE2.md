# PMM Phase 2: Intrinsic Policies and Expressive Reflections (Engineer Runbook)

This document captures the authoritative Stage policies, new/updated event kinds, and a terse runbook for verifying Phase 2 behavior. Everything is intrinsic, append-only, and deterministic.

## Stage Tables (authoritative)

### Reflection Cadence (E)

| Stage | min_turns | min_time_s | force_reflect_if_stuck |
|------:|----------:|-----------:|:-----------------------:|
| S0    | 2         | 20         | true                    |
| S1    | 3         | 35         | true                    |
| S2    | 4         | 50         | false                   |
| S3    | 5         | 70         | false                   |
| S4    | 6         | 90         | false                   |

### Drift Multipliers (F)

Only O (openness), C (conscientiousness), and N (neuroticism) participate.

| Stage | O    | C    | N    |
|------:|:----:|:----:|:----:|
| S0    | 1.00 | 1.00 | 1.00 |
| S1    | 1.25 | 1.10 | 1.00 |
| S2    | 1.10 | 1.25 | 1.00 |
| S3    | 1.00 | 1.20 | 0.80 |
| S4    | 0.90 | 1.10 | 0.70 |

## Event Glossary (new/updated kinds)

### policy_update

Emitted once per change (idempotent) by comparing to the last policy of the same component. Two components exist:

- component="reflection"

```json
{
  "kind": "policy_update",
  "meta": {
    "component": "reflection",
    "stage": "S1",
    "params": {
      "min_turns": 3,
      "min_time_s": 35,
      "force_reflect_if_stuck": true
    },
    "tick": 4
  }
}
```

- component="drift"

```json
{
  "kind": "policy_update",
  "meta": {
    "component": "drift",
    "stage": "S3",
    "params": {
      "mult": {"openness": 1.0, "conscientiousness": 1.2, "neuroticism": 0.8}
    },
    "tick": 7
  }
}
```

### insight_ready

One-shot marker that points to a prior reflection and is consumed by the next response only.

```json
{
  "kind": "insight_ready",
  "meta": {"from_event": 42, "tick": 9}
}
```

## Mini REPL Transcript (happy path)

- identity_propose → identity_adopt("Casey")
- policy_update(reflection, S0)
- debug reflect_skip ×4 → forced reflection (S0)
- reflection("I will keep answers concise") → insight_ready(from_event=<reflection_id>)
- response("…\n_Insight:_ I will keep answers concise")
- policy_update(drift, S1) after stage change
- trait_update(openness, +0.025) at S1; later trait_update(neuroticism, -0.016) at S3

## Verify Quickly (tail last 20)

Python snippet:

```python
from pmm.storage.eventlog import EventLog
log = EventLog(".data/pmm.db")
for ev in log.read_tail(limit=20):
    print(ev["id"], ev["kind"], ev["content"], ev["meta"])
```

Checklist:
- policy_update reflects current stage and changes only when params change.
- Four reflect_skip in S0/S1 can force one reflection.
- insight_ready refers to a prior reflection and is consumed by exactly one response.
- Drift deltas are scaled per stage table and rounded to 3 decimals.
