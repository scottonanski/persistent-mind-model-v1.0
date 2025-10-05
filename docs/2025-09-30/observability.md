# Observability: LLM Budgets and Latency Events

This guide documents PMM's runtime observability around LLM usage: deterministic per‑tick budgets, rate‑limit breadcrumbs, and latency metrics.

## TickBudget (deterministic per‑tick ceilings)

- Source: `pmm/llm/limits.py`
- Constants:
  - `MAX_CHAT_CALLS_PER_TICK = 4`
  - `MAX_EMBED_CALLS_PER_TICK = 20`
- Mechanism:
  - Runtime derives a `tick_id` as `1 + count(autonomy_tick)` so the budget resets deterministically per heartbeat.
  - The budget tracks per‑tick counts for `chat` and `embed` calls.

## Budgeted wrappers

- Source: `pmm/llm/factory.py`
  - `chat_with_budget(chat_fn, *, budget, tick_id, evlog, provider, model, log_latency=True)`
  - `embed_with_budget(embed_fn, *, budget, tick_id, evlog, provider, model, log_latency=True)`
- Behavior:
  - If the call would exceed the ceiling, append a breadcrumb and skip the provider call:
    - Event: `rate_limit_skip`
    - Meta: `{ op: "chat"|"embed", provider, model, tick }`
  - Otherwise execute the call and (by default) append a latency record:
    - Event: `llm_latency`
    - Meta: `{ op, provider, model, ms: float, ok: bool, tick }`
  - `log_latency=False` can be passed for sensitive paths where test‑critical event ordering must be preserved.

## Where it is wired

- Source: `pmm/runtime/loop.py`
  - `Runtime.reflect(...)` uses `chat_with_budget(...)` for the reflection model call.
  - `Runtime._propose_identity_name(...)` uses `chat_with_budget(...)` for the short name proposal call.
  - Both use a shared `TickBudget` instance on `Runtime`.

## Ordering guarantees

- Reflection flow ordering (authoritative) remains:
  - `reflection` → `reflection_check` → `[commitment_open?]` → `insight_ready` → `bandit_arm_chosen` → `autonomy_tick`
- The `llm_latency` event is a diagnostics breadcrumb. For the strict invariant test path, latency logging is disabled to avoid inserting it before `reflection`. In normal operation, `llm_latency` is emitted adjacent to the model call.
- The `rate_limit_skip` breadcrumb may appear when a budget ceiling would be exceeded. Skips are non‑fatal and the runtime falls back to deterministic, short outputs where applicable.

## Stage 4 observability: Evaluators and Planning Thought

Stage 4 introduces three new log-only events. All are deterministic, tail-based, and respect existing ordering invariants. No new write APIs or flags are added.

- `evaluation_report` (S4(A))
  - Emitted once every 5 ticks (idempotent per `component` + `tick`).
  - Placement: after `autonomy_tick` and bandit reward logging, before invariant triage.
  - Meta: `{ component: "performance", metrics: { completion_rate, bandit_accept_winrate, llm_chat_latency_mean_ms, novelty_same_ratio, window }, tick }`.
  - Example:
    ```json
    {"kind": "evaluation_report", "content": "", "meta": {
      "component": "performance",
      "metrics": {
        "completion_rate": 0.75,
        "bandit_accept_winrate": 0.6,
        "llm_chat_latency_mean_ms": 142.3,
        "novelty_same_ratio": 0.5,
        "window": 200
      },
      "tick": 510
    }}
    ```

- `evaluation_summary` (S4(C))
  - Optional short operator-facing summary that follows an `evaluation_report` for that tick.
  - Placement: immediately after the corresponding `evaluation_report` and before invariant triage.
  - Meta: `{ from_report_id, tick, stage }`.
  - Example:
    ```json
    {"kind": "evaluation_summary", "content": "Completion steady; acceptance slightly improving; latency stable.", "meta": {
      "from_report_id": 4920, "tick": 510, "stage": "S1"
    }}
    ```

- `planning_thought` (S4(B))
  - A privacy-safe mini plan logged once after each reflection in S1+ (no chain-of-thought; ≤3 bullets or ≤2 sentences).
  - Placement: after `reflection_check`/`insight_ready` and the reflection-path `bandit_arm_chosen` emission.
  - Meta: `{ from_event: <reflection_id>, tick, stage }`.
  - Example:
    ```json
    {"kind": "planning_thought", "content": "• Clarify intent in one line.\n• Keep reply under 2 sentences.\n• Ask one precise follow-up.", "meta": {
      "from_event": 4899, "tick": 509, "stage": "S2"
    }}
    ```

- `curriculum_update` (S4(D) proposal)
  - Derived from the latest `evaluation_report` with deterministic rules (no env flags):
    - If `bandit_accept_winrate < 0.25` → propose `{ component: "reflection", params: { min_turns: max(1, current-1) } }`.
    - Else if `novelty_same_ratio > 0.80` → propose `{ component: "cooldown", params: { novelty_threshold: min(1.0, current+0.05) } }`.
    - Else → no proposal.
  - "Current" parameters are read from the most recent `policy_update` for the component within a bounded tail; fallback defaults are `min_turns=2` and `novelty_threshold=0.50` if none found.
  - Placement: immediately after the `evaluation_report`/`evaluation_summary` block (same tick cadence as reports).
  - Meta: `{ proposed: { component, params }, reason, tick }`.
  - Example:
    ```json
    {"kind": "curriculum_update", "content": "", "meta": {
      "proposed": {"component": "cooldown", "params": {"novelty_threshold": 0.55}},
      "reason": "novelty_same_ratio=0.90 > 0.8",
      "tick": 515
    }}
    ```

- `trait_update` (S4(E) ratchet)
  - A monotonic, stage-aware adjustment emitted at most once per tick when gates pass.
  - Gates: ≥3 reflections since the last ratchet; last trait_update at least 5 ticks ago; single-emit per tick.
  - Deterministic hints from latest `evaluation_report` (component="performance"):
    - If `novelty_same_ratio > 0.80` → openness `+0.01`.
    - If `bandit_accept_winrate < 0.25` → conscientiousness `+0.01`; and if reflection volume is high, extraversion `-0.01`.
  - Per-stage clamps to keep traits within:
    - `RATCHET_BOUNDS[stage]` for `openness`, `conscientiousness`, `extraversion`.
  - Placement: after the curriculum bridge and before invariant triage.
  - Meta (multi-delta shape): `{ delta: { openness, conscientiousness, extraversion }, reason: "ratchet", stage, tick }`.
  - Example:
    ```json
    {"kind": "trait_update", "content": "", "meta": {
      "delta": {"openness": 0.01, "conscientiousness": 0.01, "extraversion": -0.01},
      "reason": "ratchet", "stage": "S2", "tick": 516
    }}
    ```

Policy bridge (idempotent)

- After a `curriculum_update`, the loop checks the recent tail; if no matching `policy_update` exists with identical `component` and `params` since that proposal, it appends one `policy_update`:
  - `{"kind":"policy_update","meta":{"component": <str>, "params": {…}, "tick": <int>}}`
  - If already applied, it skips (no duplicates).

Ordering invariants preserved

- Reflect path remains ordered: `reflection` → `reflection_check` → `[commitment_open?]` → `insight_ready` → `bandit_arm_chosen` → `planning_thought` (S4(B)) → ...
- Tick tail remains: `autonomy_tick` → `[bandit_reward if horizon]` → `evaluation_report` (every 5 ticks) → `evaluation_summary` (optional) → `curriculum_update` (proposal) → `policy_update` (if not already applied) → `trait_update(reason="ratchet")` (if gates pass) → invariant triage.
- Existing S2/S3 invariants hold: one `bandit_arm_chosen` per tick and `bandit_guidance_bias` precedes `bandit_arm_chosen` on both reflect and skip paths.

Cadence and idempotency

- `evaluation_report`: every 5 ticks via a stable constant; each report is idempotent for a given `component` + `tick`.
- `evaluation_summary`: idempotent per `from_report_id`.
- `planning_thought`: idempotent per `from_event` (reflection id); only emitted in S1+.
 - `curriculum_update`: runs alongside the report cadence; proposal emitted only when rules fire and differs from current params.
 - `policy_update` bridge: emitted at most once per proposal; skipped if an identical update already exists since the proposal.
 - `trait_update` (ratchet): at most one per tick; requires reflection and tick-gap gates; strictly clamped by stage bounds; no oscillation within the enforced tick gap.

API surface

- Read-only API remains unchanged; these events appear naturally in `/snapshot` responses.
- No new POST routes; all additions are append-only observability.

## Query examples

- Find all LLM latency events for chat:
  - Filter: `kind == "llm_latency" AND meta.op == "chat"`
- Find budget skips:
  - Filter: `kind == "rate_limit_skip"`

## Rationale

- Keep background loops stable and bounded.
- Provide actionable breadcrumbs for performance and capacity tuning.
- Preserve test‑sensitive ordering by allowing targeted suppression of latency logging.

---

## SQL examples (SQLite / json_extract)

These examples use SQLite JSON1 functions to project fields out of `meta`.

List the last 20 latency records (op, provider, model, ms, ok):

```sql
SELECT
  id,
  ts,
  json_extract(meta, '$.op')       AS op,
  json_extract(meta, '$.provider') AS provider,
  json_extract(meta, '$.model')    AS model,
  CAST(json_extract(meta, '$.ms') AS REAL) AS ms,
  CAST(json_extract(meta, '$.ok') AS INT)  AS ok
FROM events
WHERE kind = 'llm_latency'
ORDER BY id DESC
LIMIT 20;
```

Average latency by provider+model:

```sql
WITH t AS (
  SELECT
    json_extract(meta, '$.provider') AS provider,
    json_extract(meta, '$.model')    AS model,
    CAST(json_extract(meta, '$.ms') AS REAL) AS ms
  FROM events
  WHERE kind = 'llm_latency'
)
SELECT provider, model, ROUND(AVG(ms), 1) AS avg_ms, COUNT(*) AS n
FROM t
GROUP BY provider, model
ORDER BY avg_ms DESC;
```

Approximate p95 latency per provider+model (order-statistic):

```sql
WITH t AS (
  SELECT
    json_extract(meta, '$.provider') AS provider,
    json_extract(meta, '$.model')    AS model,
    CAST(json_extract(meta, '$.ms') AS REAL) AS ms
  FROM events
  WHERE kind = 'llm_latency'
), ranked AS (
  SELECT
    provider, model, ms,
    ROW_NUMBER() OVER (PARTITION BY provider, model ORDER BY ms) AS rn,
    COUNT(*)    OVER (PARTITION BY provider, model)               AS total
  FROM t
)
SELECT provider, model,
       (SELECT ms FROM ranked r2
        WHERE r2.provider = ranked.provider AND r2.model = ranked.model
        ORDER BY ms
        LIMIT 1 OFFSET CAST(0.95 * (ranked.total - 1) AS INT)) AS p95_ms,
       total AS samples
FROM ranked
GROUP BY provider, model
ORDER BY p95_ms DESC;
```

Recent rate-limit skips by op (chat/embed):

```sql
SELECT op, COUNT(*) AS skips
FROM (
  SELECT json_extract(meta, '$.op') AS op
  FROM events
  WHERE kind = 'rate_limit_skip'
  ORDER BY id DESC
  LIMIT 1000
)
GROUP BY op
ORDER BY skips DESC;
```

Per-tick chat call counts (from latency breadcrumbs):

```sql
SELECT tick, COUNT(*) AS chat_calls
FROM (
  SELECT CAST(json_extract(meta, '$.tick') AS INT) AS tick
  FROM events
  WHERE kind = 'llm_latency' AND json_extract(meta, '$.op') = 'chat'
)
GROUP BY tick
ORDER BY tick DESC
LIMIT 50;
```

Per-tick budget skips (when ceilings were exceeded):

```sql
SELECT tick, COUNT(*) AS skips
FROM (
  SELECT CAST(json_extract(meta, '$.tick') AS INT) AS tick
  FROM events
  WHERE kind = 'rate_limit_skip'
)
GROUP BY tick
ORDER BY tick DESC
LIMIT 50;
```

Using the sqlite3 CLI against the default database path:

```bash
sqlite3 .data/pmm.db \
  -cmd ".mode column" -cmd ".headers on" \
  "SELECT id, ts, json_extract(meta, '$.op') op, json_extract(meta, '$.ms') ms FROM events WHERE kind='llm_latency' ORDER BY id DESC LIMIT 10;"
```

## Without JSON1: Python projection

If your SQLite build lacks JSON1, you can project meta fields in Python and run numeric analyses there:

```python
import json
import sqlite3

conn = sqlite3.connect('.data/pmm.db')
cur = conn.execute("SELECT id, ts, kind, meta FROM events WHERE kind IN ('llm_latency','rate_limit_skip') ORDER BY id DESC LIMIT 1000")
rows = []
for rid, ts, kind, meta_json in cur.fetchall():
    try:
        m = json.loads(meta_json) if meta_json else {}
    except Exception:
        m = {}
    rows.append({
        'id': rid,
        'ts': ts,
        'kind': kind,
        'op': m.get('op'),
        'provider': m.get('provider'),
        'model': m.get('model'),
        'ms': float(m.get('ms') or 0.0),
        'ok': bool(m.get('ok')),
        'tick': m.get('tick')
    })

# Example: average chat latency
chat = [r['ms'] for r in rows if r['kind']=='llm_latency' and r['op']=='chat']
avg = sum(chat)/len(chat) if chat else 0.0
print(f"avg chat ms: {avg:.1f} over {len(chat)} samples")
```
