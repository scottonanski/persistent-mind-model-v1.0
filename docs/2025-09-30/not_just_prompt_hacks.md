# Why PMM Isn’t “Just Prompt Hacks” 🚀

> PMM (Prompted Machine Model) is far more than a collection of clever prompt tricks. It’s a robust, structured system with a ledger-first architecture, autonomous control loops, and rigorous validation mechanisms. Below, we break down the core components and explain why PMM isn't just simple prompt engineering. 🌟

---

## Core Orientation Definition 📜

_The foundation of PMM’s prompt system is defined in:_

- **Source**: `pmm/runtime/pmm_prompts.py`
- **Functions**: `orientation_text()`, `voice_constraints()`, `build_system_msg()`.
- **Includes hash utilities** (`orientation_hash()`) and legacy export `PMM_ORIENTATION` for auditability. 🔍

## Where the System Prompt Gets Applied 🛠️

- **Runtime loop**: `pmm/runtime/loop.py`
  - Injects `build_system_msg("chat")` for user-facing turns.
  - Uses `build_system_msg("reflection")` for internal reflections (see `Runtime.handle_user_prompt()` near line ~1950 for message assembly and reflection triggers).
- **Emergence scoring**: `pmm/runtime/emergence.py`
  - Wraps reflection scoring prompts with `build_system_msg('reflection')`.
- **Planning helper**: `pmm/runtime/planning.py`
  - Starts planning prompts with `build_system_msg('planning')`.
- **Stage-specific reflections**: `pmm/runtime/loop.py` (stage tracker section)
  - Concatenates `build_system_msg("reflection")` with stage guidance text.
- **Other prompt constants**:
  - Introspection summaries use a fixed template in `pmm/runtime/introspection.py` (`_INTROSPECTION_PROMPT_TEMPLATE`).
  - Operator guardrails (`DECISION_PROBE_PROMPT`, `GATE_CHECK_PROMPT`) are defined in `pmm/runtime/validators.py`.
  - Canary prompts (`CANARIES`) live in `pmm/runtime/canaries.py` for regression checks.

---

## Unit Coverage 🧪

Tests referencing these prompts sit in:

- `tests/test_reflection_prompts.py`
- `tests/test_introspection_prompt_shape.py`
- `tests/test_handle_user_prompt.py`

These confirm expectations about prompt shapes and catch drift early. ✅

---

PMM’s strength lies in its structured, data-driven architecture, not in fragile prompt engineering. Key pillars:

## Ledger-First Architecture 📒

- **State changes** (identity, traits, policies, commitments) pass through append-only events (`pmm/storage/eventlog.py`) and projections (`pmm/storage/projection.py`).
- **Prompts remind** the model of the contract; enforcement happens in code that rejects inconsistent actions (e.g., `validate_decision_probe()` and metrics verification in `pmm/runtime/validators.py`).
- **IAS/GAS** recomputation in `pmm/runtime/metrics.py` ensures consistency. 🛡️

## Autonomy Loop as Control System 🔄

- `pmm/runtime/loop.py` orchestrates:
  - Background ticks.
  - Gating reflections via `ReflectionCooldown`.
  - Emitting `autonomy_tick` events.
  - Recomputing telemetry and running evaluators.
- These mechanics operate independently of LLM text, relying on histories, cadences, and scheduled work. ⚙️

## Separate Evaluators and Bandits 🎰

- Components such as `pmm/runtime/reflection_bandit.py`, `pmm/runtime/evaluators/performance.py`, and `pmm/runtime/self_evolution.py` analyze ledger data and drive adjustments.
- They leverage learned statistics, embeddings (`pmm/runtime/memegraph.py`), and scoring thresholds—not handcrafted prompts. 📈

## External Validation ✅

- **Canaries**: Deterministic spot checks in `pmm/runtime/canaries.py`.
- **Validators**: Block malformed reflections or metric leakage via the validator suite.

---

## The Big Picture 🌍

Together, the prompts are thin orientation layers atop a governed, instrumented runtime that enforces behavior through:

- **Data structures**: Ledger and projections.
- **Validators**: Robust checks and balances.
- **Background processing**: Autonomous loops and evaluators.

Even if an LLM went off-script, safeguards and metrics (e.g., the IAS loop fixes) keep the system on track. This is the opposite of fragile “prompt hacks”—it’s a resilient, principled architecture built for reliability and scalability. 💪