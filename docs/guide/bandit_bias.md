# Bandit Bias (Step 15)

Intent: apply a small, deterministic nudge from structured guidance to the bandit arm selection.

Constants:
- `EPS_BIAS = 0.03` (per-arm clamp)
- `ARM_FROM_GUIDANCE_TYPE = { "checklist": "checklist", "succinct": "succinct", "narrative": "narrative", "question": "question_form", "analytical": "analytical" }`

Trace:
- Each tick logs **one** `bandit_guidance_bias` (with `meta.delta`, `meta.items`)
- Then `bandit_arm_chosen`

No keywords/regex. If a guidance item lacks `type` or `score`, it has **no effect**.

**Determinism**

- No keyword/regex parsing.
- Replay-stable: same input → same bias → same arm.
