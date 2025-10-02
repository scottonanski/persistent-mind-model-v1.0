from __future__ import annotations

from typing import Any

from pmm.storage.projection import build_directives_active_set

GUIDANCE_MAX = 5  # small, fixed; no flags


def build_reflection_guidance(
    events: list[dict], top_k: int = GUIDANCE_MAX
) -> dict[str, Any]:
    """
    Deterministic guidance for reflection, based on active directives.
    Returns {"text": str, "items": [{"content", "score"}...]}.
    """
    active = build_directives_active_set(events)[: max(0, int(top_k))]
    items = [{"content": r["content"], "score": r["score"]} for r in active]
    if not items:
        return {"text": "", "items": []}

    # Minimal, stable formatting
    parts = [f"- {it['content']}" for it in items]
    text = "Guidance:\n" + "\n".join(parts)
    return {"text": text, "items": items}
