from __future__ import annotations

from typing import Any


def get_content_meta(ev: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    Read-tolerant accessor: prefers top-level content/meta; falls back to payload.content/meta.
    Never raises; returns ("", {}) if absent.
    """
    payload = ev.get("payload") or {}
    content = ev.get("content", None)
    if content is None:
        content = payload.get("content", "")
    meta = ev.get("meta", None)
    if meta is None:
        meta = payload.get("meta", {}) or {}
    return str(content or ""), dict(meta or {})
