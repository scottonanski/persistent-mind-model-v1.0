"""Commitments tracker facade package.

Stage 1: This package re-exports the legacy tracker module to preserve the
existing import surface while introducing an `api` module for the split plan.
"""

from __future__ import annotations

import importlib as _importlib
from collections.abc import Iterable
from typing import Any

_legacy = _importlib.import_module(__name__ + ".legacy")

for _n in dir(_legacy):
    if _n.startswith("__") and _n.endswith("__"):
        continue
    globals()[_n] = getattr(_legacy, _n)
del _n


def __getattr__(name: str) -> Any:  # pragma: no cover - passthrough
    return getattr(_legacy, name)


def __dir__() -> Iterable[str]:  # pragma: no cover - passthrough
    return sorted(set(list(globals().keys()) + dir(_legacy)))


try:  # Prefer local scaffolding API
    from . import api as api  # type: ignore
except Exception:
    try:  # pragma: no cover - optional external wiring
        from pmm.commitments.tracker_pkg import api as api  # type: ignore
    except Exception:  # pragma: no cover - optional wiring
        api = None  # type: ignore


__all__ = [
    name
    for name in globals().keys()
    if not (name.startswith("__") and name.endswith("__"))
]
