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


# Idempotent policy_update emission keyed by (component, params, stage)
def append_policy_update_once(
    eventlog,
    *,
    component: str,
    params: dict | None = None,
    stage: str | None = None,
    tick: int | None = None,
    window: int = 100,
) -> bool:
    key = {
        "component": str(component),
        "params": dict(params or {}),
        "stage": str(stage) if stage is not None else None,
    }
    meta = {
        "component": str(component),
        "stage": stage,
        "tick": tick,
    }
    return append_once(
        eventlog,
        kind="policy_update",
        content="",
        meta=meta,
        key=key,
        window=window,
    )
