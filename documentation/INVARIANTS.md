# Event ↔ Invariant Crosswalk

This links event kinds to the deterministically enforced checks that keep the ledger coherent.

Primary sources:
- Runtime invariants: `pmm/runtime/invariants.py:1`
- Integrity checks: `pmm/runtime/invariants_rt.py:1`

## Ledger Shape (all events)
- Monotonic increasing `id`; no duplicates
- `kind` is string; `meta` is dict
- Hash chain verification (optional): `EventLog.verify_chain()` → `HASH_CHAIN`

## Identity
- `identity_adopt`
  - Name must sanitize to a valid token → `identity:adopted_name_invalid`
  - First `response` after adopt when next adopt is adjacent → `renderer:missing_first_response_after_adopt`
- `identity_propose`
  - Grace window of ≤5 proposals without adopt → `identity:multiple_proposals_without_adopt`
- `identity_clear`
  - Explicit clear to avoid strict revert errors in strict projection

## Traits
- `trait_update`
  - No drift before first `identity_adopt` → `drift:trait_update_before_adopt`
  - Per-reason spacing by `meta.tick` (≥5) → `drift:rate_limit_violation`
  - Projection clamps deltas to [0,1] (strict bounds optional)

## Commitments & Evidence
- `commitment_open`
  - Populates open map; TTL/expire assessed later
- `evidence_candidate`
  - No adjacent duplicate `{cid, snippet}` → `evidence:duplicate_adjacent_candidate`
- `commitment_close`
  - Requires prior `evidence_candidate` after last open → `evidence:close_without_candidate`
- `commitment_expire`
  - Must reference an open commitment → `ttl:expire_without_open`

Integrity shortcuts (invariants_rt):
- `CANDIDATE_BEFORE_CLOSE` (close without candidate)
- `TTL_OPEN_COMMITMENTS` (open past expire_at/ttl)

## Insights & Scenes
- `insight_ready`
  - References prior `reflection` and consumed exactly once by next `response` block → `insight:without_preceding_reflection`, `insight:unconsumed`, `insight:over_consumed`
- `scene_compact`
  - `source_ids` are prior, strictly increasing, match `window.start/end`; content ≤ 500; no duplicate windows → `scene:*`

## Recall Suggestions
- `recall_suggest`
  - EIDs exist, are prior, unique, and ≤3 total → `recall:*`

## Bandit
- `bandit_reward`
  - Reward in [0,1] and prior matching `bandit_arm_chosen` → `bandit:reward_out_of_bounds`, `bandit:reward_without_prior_arm`

## Embeddings
- `embedding_indexed`
  - Points to prior event (`eid`), carries digest, no duplicate digest per `eid` → `embedding:*`
- `embedding_skipped`
  - Must have empty meta → `embedding:skipped_has_meta`

## Policies & Stage Coherence
- `policy_update`
  - No consecutive duplicates (component, params) → `policy:duplicate_policy_update`
  - Stage must match contemporaneous inference → `policy:stage_mismatch`
  - Component schema checks (reflection cadence, drift multipliers) → `policy:*_schema_invalid`

## Metrics & Stage
- `autonomy_tick`, `reflection`
  - Telemetry (`IAS`, `GAS`) used for windowed stage inference with hysteresis (`pmm/runtime/stage_tracker.py:1`)
- `metrics_update`, `gas_breakdown`
  - Emitted by metrics system (`pmm/runtime/metrics.py:1`), consumed by API/UI

