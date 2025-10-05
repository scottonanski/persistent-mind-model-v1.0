"""Runtime loop API (Stage 1 scaffolding).

This module is a placeholder for the stable public entrypoints described in
docs/splits/loop-split-plan.md. It intentionally does not modify behavior or
imports. Existing callers should continue importing from `pmm.runtime.loop`.

In later stages, functions/classes here will be wired by the `pmm.runtime.loop`
facade to preserve behavior while reducing coupling inside the loop.
"""

from __future__ import annotations

from typing import Any


def not_ready(
    *_args: Any, **_kwargs: Any
) -> None:  # pragma: no cover - scaffolding only
    """Temporary no-op placeholder.

    This function exists to anchor the API surface without affecting current
    behavior. It will be replaced with real implementations as we extract
    components per the split plan.
    """

    return None


__all__ = [
    "not_ready",
]
