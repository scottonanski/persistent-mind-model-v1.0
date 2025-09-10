"""Core PMM invariants (public shim).

Intent:
- Define and expose system-wide invariants from a stable import path.
- For the live implementation, see :mod:`pmm.runtime.invariants`.

Runtime implementation:
- check_invariants(events: list[dict]) -> list[str]
  - Ledger shape, identity invariants, renderer order, commitments exact match,
    trait drift gating and per-reason spacing.
"""

# Re-export the live implementation so callers can import from core invariants.
from pmm.runtime.invariants import check_invariants  # noqa: F401

__all__ = ["check_invariants"]
