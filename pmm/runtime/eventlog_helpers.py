from __future__ import annotations

import hashlib
import json
from typing import Any


def append_once(
    eventlog,
    *,
    kind: str,
    content: str | None,
    meta: dict | None,
    key: dict[str, Any],
    window: int = 100,
) -> bool:
    """Append event iff no recent event with same digest(key). Returns True if appended."""
    blob = json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()[:16]
    reader = getattr(eventlog, "read_tail", None)
    if reader is None:
        recent = []
    else:
        try:
            recent = reader(limit=window)
        except TypeError:
            recent = reader(window)
    for ev in reversed(recent):
        if ev.get("kind") != kind:
            continue
        if (ev.get("meta") or {}).get("digest") == digest:
            return False
    m = dict(meta or {})
    m["digest"] = digest
    eventlog.append(kind, content or "", m)
    return True
