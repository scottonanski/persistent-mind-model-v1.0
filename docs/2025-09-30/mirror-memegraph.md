# Mirror & MemeGraph Overview

## Purpose

- Provide fast, deterministic access to ledger state without replaying the full SQLite log each turn.
- Maintain a structural graph projection so relationship-heavy lookups are O(k) instead of O(N).
- Keep the ledger (`.data/pmm.db`) the single authority; both layers rebuild deterministically from it.

## Ledger Mirror

- **Implementation**: `pmm/runtime/snapshot.py` defines the immutable `LedgerSnapshot` used by the runtime.
- **Construction**: `Runtime._get_snapshot()` (`pmm/runtime/loop.py:447-485`) reads the event log, builds identity/self models, and caches the snapshot behind `_snapshot_lock`; append listeners invalidate the cache.
- **Benefit**: Eliminates repeated `EventLog.read_all()` scans in StageManager, CommitmentTracker, policy gating, etc., by providing an O(Δ) cache.
- **Evidence**:
  - Snapshot dataclass fields: `pmm/runtime/snapshot.py:8-17`.
  - Cache guard and invalidation: `pmm/runtime/loop.py:447-485`.
  - Tests depending on deterministic snapshots: `tests/test_stage_manager.py`, `tests/test_commitments.py`.

## MemeGraph Projection

- **Implementation**: `pmm/runtime/memegraph.py` contains `MemeGraphProjection`, indexing events into hashed nodes/edges and tracking incremental state.
- **Data captured**: nodes for events, identities, commitments, reflections, policies, stages, bandit events; edges like `transition`, `references:policy_update`, etc. Open commitments and latest stage are kept in-memory.
- **Telemetry**: `_record_metrics` (`pmm/runtime/memegraph.py:132-160`) records batch length, duration, node/edge counts, RSS; exposed via `last_batch_metrics`.
- **Runtime queries**:
  - Stage: `latest_stage()` → `StageManager.current_stage()` (`pmm/runtime/stage_manager.py:24-37`).
  - Commitments: `open_commitments_snapshot()` → `CommitmentTracker._rebind_commitments_on_identity_adopt()` (`pmm/commitments/tracker.py:120-143`).
  - Policy links: `policy_updates_for_reflection()` → `maybe_reflect()` (`pmm/runtime/loop.py:2838-2865`).
- **Evidence**:
  - Initialization & append listener: `pmm/runtime/memegraph.py:61-88`.
  - Deterministic node/edge hashing: `_ensure_node` / `_ensure_edge` (`pmm/runtime/memegraph.py:332-370`).
  - Tests: `tests/test_memegraph.py`, plus Stage/Commitment/Reflection tests listed above.

## Runtime Wiring

- `Runtime.__init__` instantiates the graph (`pmm/runtime/loop.py:373-425`) and threads it through StageManager, CommitmentTracker, autonomy loop, and reflection code paths.
- StageManager prefers graph state with legacy replay as debug fallback (`pmm/runtime/stage_manager.py:24-37`).
- CommitmentTracker compares legacy vs. graph open maps (`pmm/commitments/tracker.py:120-143`).
- Reflection policy checks cross-validate via graph lookups (`pmm/runtime/loop.py:2838-2865`).

## Verification

| Claim | Evidence |
| ----- | -------- |
| Mirror snapshot prevents redundant ledger scans | Cache logic `pmm/runtime/loop.py:447-485`; full suite passes (`venv/bin/python -m pytest`). |
| MemeGraph rebuilds deterministically | `rebuild()` replay (`pmm/runtime/memegraph.py:106-124`); digest-based storage (`pmm/runtime/memegraph.py:332-370`). |
| Graph powers stage/commitment/policy queries | `pmm/runtime/stage_manager.py:24-37`; `pmm/commitments/tracker.py:120-143`; `pmm/runtime/loop.py:2838-2865`. |
| Telemetry available for monitoring | `last_batch_metrics` (`pmm/runtime/memegraph.py:101-107`). |
| Integration is stable | `tests/test_memegraph.py`, `tests/test_stage_manager.py`, `tests/test_commitments.py`, `tests/test_reflection_runtime.py`, `tests/test_identity.py` (532 passed, 2 skipped). |

## Operational Notes

- The ledger remains authoritative; deleting mirror/graph caches and calling `MemeGraphProjection.rebuild()` reproduces state from the log.
- Both layers rely on EventLog append listeners—new event kinds should extend projection handlers to retain parity.
- Monitor `last_batch_metrics` to ensure per-event overhead stays within performance budgets.
