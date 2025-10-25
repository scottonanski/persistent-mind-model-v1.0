# Kernel Update Documentation

This folder tracks the progress and communications related to the development of the EvolutionKernel prototype for the Persistent Mind Model (PMM) project.

## Overview
- **Objective**: Develop a central `EvolutionKernel` to integrate reflections, commitments, and metrics for end-to-end identity evolution.
- **Branch**: `feature/kernel-update`
- **Key Dates**: Started on October 22, 2025

## Progress Logs
- **Initial Plan**: Focus on feedback loops, narrative cohesion, and metric integration (Oct 22, 2025).
- **Prototype Creation**: Created `evolution_kernel.py` with initial structure for `EvolutionKernel` class, including methods for identity evaluation, reflection triggering, and identity adjustments (Oct 22, 2025).
- **Core Logic Implementation**: Implemented detailed logic for feedback loops (commitment analysis for trait adjustments), reflection triggers (content generation based on state), and identity adjustments (narrative context from historical data) in `EvolutionKernel` (Oct 22, 2025).
- **Runtime Integration**: Wired `EvolutionKernel` into the autonomy tick so kernel feedback can drive reflection forcing, trait targets, and telemetry via new `identity_adjust_proposal` events (Oct 22, 2025).
- **Architectural Updates**: Normalized trait keying with `traits.py`, lifted magic numbers into `policy/evolution.py`, and drafted event hygiene spec in `docs/kernel-update/event_hygiene.md` for consistency and auditability (Oct 22, 2025).
- **Reflection Cadence Source of Truth**: Established `CADENCE_BY_STAGE` as the definitive source for reflection cadence with documentation in `docs/kernel-update/reflection_cadence.md`, including rationale for overrides (Oct 22, 2025).
- **EvolutionKernel Responsibilities**: Codified the advisory role of `EvolutionKernel` in docstrings and this README, emphasizing its responsibility to evaluate, propose, and optionally request reflections without directly mutating the ledger beyond forced reflections (Oct 22, 2025).
- **Final Architectural Updates**: Confirmed policy module path at `pmm/runtime/policy/evolution.py`, added trait keying contract, documented policy defaults, and linked event hygiene spec (Oct 22, 2025).

## EvolutionKernel Responsibilities

- **Advisory Role**: The `EvolutionKernel` evaluates the current state of identity, commitments, and metrics to propose adjustments to traits or identity, which are then consumed by autonomy components for action.
- **Proposal Generation**: It generates proposals for trait adjustments or identity changes, ensuring a cohesive narrative for evolution.
- **Reflection Triggering**: It may request reflections based on its evaluations, but only emits its own reflection events when explicitly forced.
- **Non-Mutative Design**: Beyond emitting forced reflections, it does not directly mutate the ledger; all other changes are proposals for other components to act upon, maintaining a clear separation of concerns.

## Architectural Contracts and Defaults

All trait keys are lowercase; call `traits.normalize_key()` on read/write.

| Policy Parameter              | Default |
| ----------------------------- | ------- |
| `closure_rate_high`           | 0.8     |
| `closure_rate_low`            | 0.2     |
| `conscientiousness_delta_high` | 0.05    |
| `conscientiousness_delta_low` | -0.05   |
| `ias_threshold`               | 0.3     |
| `gas_threshold`               | 0.3     |
| `open_commitments_threshold`  | 5       |
| `recent_events_window`        | 50      |

- **Event Hygiene Spec**: The authoritative spec for event emission guarantees and deduplication patterns is available at [`event_hygiene.md`](event_hygiene.md).

## Communication Logs
- Initial discussion with Cascade on prioritizing the EvolutionKernel prototype.

Further updates and detailed design documents will be added as development progresses.
