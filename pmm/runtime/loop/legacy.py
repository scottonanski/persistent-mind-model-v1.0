"""Dynamic loader for legacy loop module.

Loads the original `pmm/runtime/loop.py` source file and re-exports its
attributes. This keeps behavior identical while enabling a package facade at
`pmm.runtime.loop`.
"""

from __future__ import annotations

import importlib.util as _util
import pathlib as _pathlib
import sys as _sys

_THIS_DIR = _pathlib.Path(__file__).resolve().parent
_LEGACY_PATH = _THIS_DIR.parent / "loop.py"

_SPEC = _util.spec_from_file_location("pmm.runtime._loop_legacy", str(_LEGACY_PATH))
if _SPEC and _SPEC.loader:  # pragma: no cover - import-time wiring
    _MODULE = _util.module_from_spec(_SPEC)
    _sys.modules.setdefault("pmm.runtime._loop_legacy", _MODULE)
    _SPEC.loader.exec_module(_MODULE)
    for _name in dir(_MODULE):
        if _name.startswith("__") and _name.endswith("__"):
            continue
        globals()[_name] = getattr(_MODULE, _name)
    del _name
else:  # pragma: no cover - defensive path
    raise ImportError("Failed to load legacy loop module from loop.py")
