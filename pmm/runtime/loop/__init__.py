"""Runtime loop facade package.

Stage 2: Pre-load submodules to enable clean modularization.
This approach avoids circular imports while preserving import semantics.
"""

from __future__ import annotations

import pathlib as _pathlib

# Pre-load submodules to avoid circular imports during lazy loading
from . import (
    assessment,
    constraints,
    handlers,
    identity,
    io,
    pipeline,
    reflection,
    scheduler,
    traits,
    validators,
)

__all__ = [
    "assessment",
    "constraints",
    "handlers",
    "identity",
    "io",
    "pipeline",
    "reflection",
    "scheduler",
    "traits",
    "validators",
    "api",
    "services",
]

# Stage 1 placeholders for split modules (scaffolding only)
try:  # pragma: no cover - optional wiring
    from pmm.runtime.loop_pkg import api as api  # type: ignore
    from pmm.runtime.loop_pkg import services as services  # type: ignore
except Exception:  # pragma: no cover - optional wiring
    api = None  # type: ignore
    services = None  # type: ignore

_THIS_DIR = _pathlib.Path(__file__).resolve().parent
_LEGACY_PATH = _THIS_DIR.parent / "loop.py"

# Lazy loading state
_loaded = False
_legacy_module = None


def _ensure_loaded():
    """Load the legacy loop.py module on first access."""
    global _loaded, _legacy_module
    if _loaded:
        return

    # Execute the legacy module source in this package's globals
    _src = _LEGACY_PATH.read_text(encoding="utf-8")
    _legacy_globals = {}
    exec(compile(_src, str(_LEGACY_PATH), "exec"), _legacy_globals, _legacy_globals)

    # Update this package's globals with legacy symbols for backward compatibility
    globals().update(_legacy_globals)
    _loaded = True


def __getattr__(name):
    """Module-level __getattr__ for Python 3.7+ lazy loading."""
    _ensure_loaded()
    return globals().get(name)


def __dir__():
    """Module-level __dir__ for Python 3.7+ lazy loading."""
    _ensure_loaded()
    return list(globals().keys())
