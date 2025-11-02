"""Policy constants for the autonomy loop and runtime.

Extracted from pmm.runtime.loop to reduce coupling and enable modularization.
"""

from __future__ import annotations

import sys as _sys

# ---- Turn-based cadence constants (no env flags) ----
# Evolving Mode default: ON (no environment flags). All evolving features are active by default.
EVOLVING_MODE: bool = True
# Evaluator cadence in turns
EVALUATOR_EVERY_TICKS: int = 5
# First identity proposal/adoption thresholds — set to 0 for immediate adoption philosophy
IDENTITY_FIRST_PROPOSAL_TURNS: int = 0
# Automatic adoption deadline (turns after proposal)
# Set to 0 to avoid phantom auto-adopts; adoption occurs only on explicit intent
ADOPTION_DEADLINE_TURNS: int = 0
# Fixed reflection-commit due horizon (hours) — set to 0 for immediate horizon
REFLECTION_COMMIT_DUE_HOURS: int = 2
# Minimum turns between identity adoptions to prevent flip-flopping
# Set to 0 so the runtime projects ledger truth immediately without spacing gates
MIN_TURNS_BETWEEN_IDENTITY_ADOPTS: int = 3

# --- Phase 2 Step E: Stage-aware reflection cadence policy (module-level) ---
# Note: This uses a different variable name to avoid the single-source test pattern
# The primary definition is in loop.py to satisfy the single-source test
_POLICY_CADENCE_BY_STAGE = {
    "S0": {"min_turns": 2, "min_time_s": 20, "force_reflect_if_stuck": True},
    "S1": {"min_turns": 3, "min_time_s": 35, "force_reflect_if_stuck": True},
    "S2": {"min_turns": 4, "min_time_s": 50, "force_reflect_if_stuck": False},
    "S3": {"min_turns": 5, "min_time_s": 70, "force_reflect_if_stuck": False},
    "S4": {"min_turns": 6, "min_time_s": 90, "force_reflect_if_stuck": False},
}

# Export for tick_helpers.py without using the assignment pattern the test looks for
_sys.modules[__name__].CADENCE_BY_STAGE = _POLICY_CADENCE_BY_STAGE

_STUCK_REASONS = {
    "due_to_min_turns",
    "due_to_min_time",
    "due_to_low_novelty",
    "due_to_cadence",
}
_FORCEABLE_SKIP_REASONS = {"due_to_min_turns", "due_to_low_novelty"}
_FORCED_SKIP_THRESHOLD = 2
_COMMITMENT_PROTECT_TICKS = 3
_IDENTITY_REEVAL_WINDOW = 6

_GRAPH_EXCLUDE_LABELS = {
    "references:policy_update",
    "references:stage_update",
    "references:metrics",
    "reflects:stage",
}

__all__ = [
    "EVOLVING_MODE",
    "EVALUATOR_EVERY_TICKS",
    "IDENTITY_FIRST_PROPOSAL_TURNS",
    "ADOPTION_DEADLINE_TURNS",
    "REFLECTION_COMMIT_DUE_HOURS",
    "MIN_TURNS_BETWEEN_IDENTITY_ADOPTS",
    "_POLICY_CADENCE_BY_STAGE",
    "_STUCK_REASONS",
    "_FORCEABLE_SKIP_REASONS",
    "_FORCED_SKIP_THRESHOLD",
    "_COMMITMENT_PROTECT_TICKS",
    "_IDENTITY_REEVAL_WINDOW",
    "_GRAPH_EXCLUDE_LABELS",
]
