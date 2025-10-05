"""Stage 1 scaffolding for the commitments tracker split.

This temporary package provides a safe home for the upcoming tracker split as
described in docs/splits/commitments-tracker-split-plan.md. It does not change
behavior or import surfaces. Existing code continues to import from
`pmm.commitments.tracker`.

The final target is a `pmm/commitments/tracker/` package with submodules like
types, ttl, due, store, indexes, and api. We use `tracker_pkg` during Stage 1
to avoid overshadowing the current module.
"""

__all__ = [
    "api",
]
