from __future__ import annotations

from typing import Any

from pmm.storage.projection import build_directives_active_set

GUIDANCE_MAX = 5  # small, fixed; no flags


def build_reflection_guidance(
    events: list[dict], top_k: int = GUIDANCE_MAX
) -> dict[str, Any]:
    """
    Deterministic guidance for reflection, based on active directives.
    Returns {"text": str, "items": [{"content", "score", "type"}...]}.

    Infers "type" from content keywords to enable guidance bias in bandit.
    """
    active = build_directives_active_set(events)[: max(0, int(top_k))]

    # Add "type" field for guidance bias compatibility
    items = []
    for r in active:
        content = r["content"]
        content_lower = content.lower()

        # Infer type from content keywords
        if "checklist" in content_lower or "list" in content_lower:
            type_hint = "checklist"
        elif "question" in content_lower or "ask" in content_lower or "?" in content:
            type_hint = "question"
        elif (
            "analyze" in content_lower
            or "analytical" in content_lower
            or "examine" in content_lower
        ):
            type_hint = "analytical"
        elif (
            "story" in content_lower
            or "narrative" in content_lower
            or "describe" in content_lower
        ):
            type_hint = "narrative"
        else:
            type_hint = "succinct"

        items.append({"content": content, "score": r["score"], "type": type_hint})

    if not items:
        return {"text": "", "items": []}

    # Minimal, stable formatting
    parts = [f"- {it['content']}" for it in items]
    text = "Guidance:\n" + "\n".join(parts)
    return {"text": text, "items": items}
