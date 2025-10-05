"""Runtime loop facade package.

Stage 1: Execute the legacy `pmm/runtime/loop.py` into this package namespace to
preserve the exact import/mocking semantics, while providing `api` and
`services` placeholders for the split (no behavior change).
"""

from __future__ import annotations

import pathlib as _pathlib

_THIS_DIR = _pathlib.Path(__file__).resolve().parent
_LEGACY_PATH = _THIS_DIR.parent / "loop.py"

# Execute the legacy module source in this package's globals so that
# monkeypatches against `pmm.runtime.loop` affect the same globals used by the
# implementation (matching pre-split behavior).
_src = _LEGACY_PATH.read_text(encoding="utf-8")
exec(compile(_src, str(_LEGACY_PATH), "exec"), globals(), globals())

# Stage 1 placeholders for split modules (scaffolding only)
try:  # pragma: no cover - optional wiring
    from pmm.runtime.loop_pkg import api as api  # type: ignore
    from pmm.runtime.loop_pkg import services as services  # type: ignore
except Exception:  # pragma: no cover - optional wiring
    api = None  # type: ignore
    services = None  # type: ignore
