"""Stage 1 scaffolding for the runtime loop split.

This temporary package provides a safe, non-conflicting home for the future
runtime loop split (see docs/splits/loop-split-plan.md). It does not change
behavior or import surfaces. Existing code continues to import from
`pmm.runtime.loop`.

Submodules:
- api: Stable entrypoints to be adopted by the facade in a later stage
- services: Explicit dependency wiring to avoid import cycles

Note: We use the name `loop_pkg` during Stage 1 to avoid overshadowing the
existing `pmm.runtime.loop` module. Once the extraction is ready, the plan is
to migrate to `pmm/runtime/loop/` and keep a compatibility facade.
"""

__all__ = [
    "api",
    "services",
]
