# Analysis of pmm/runtime/loop.py

## Top-level definitions in loop.py (30)

- def _compute_trait_nudges_from_text
- def _compute_reflection_due_epoch
- def _has_reflection_since_last_tick
- def _vprint
- def _sha256_json
- def _append_embedding_skip
- def _count_words
- def _wants_exact_words
- def _wants_no_commas
- def _wants_bullets
- def _forbids_preamble
- def _strip_voice_wrappers
- class Runtime
- def _sanitize_name
- def _affirmation_has_multiword_tail
- def evaluate_reflection
- def _append_reflection_check
- def _resolve_reflection_cadence
- def _resolve_reflection_policy_overrides
- def _maybe_emit_meta_reflection
- def _maybe_emit_self_assessment
- def _apply_self_assessment_policies
- def _maybe_rotate_assessment_formula
- def generate_system_status_reflection
- def emit_reflection
- def maybe_reflect
- def _consecutive_reflect_skips
- def _detect_self_named
- def _last_policy_params
- class AutonomyLoop

## Overlaps with other files

### pmm/runtime/reflection_bandit.py

| Overlapping Definitions |
|--------------------------|
| def emit_reflection |

### pmm/runtime/emergence.py

| Overlapping Definitions |
|--------------------------|
| def _last_policy_params |

### pmm/runtime/evaluators/curriculum.py

| Overlapping Definitions |
|--------------------------|
| def _last_policy_params |

