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

## Query examples

- Find all LLM latency events for chat:
  - Filter: `kind == "llm_latency" AND meta.op == "chat"`
- Find budget skips:
  - Filter: `kind == "rate_limit_skip"`

## Rationale

- Keep background loops stable and bounded.
- Provide actionable breadcrumbs for performance and capacity tuning.
- Preserve test‑sensitive ordering by allowing targeted suppression of latency logging.
