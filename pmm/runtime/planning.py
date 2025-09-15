from __future__ import annotations
from typing import Callable, Optional
import re

# Public API:
# maybe_append_planning_thought(eventlog, chat, *, from_reflection_id, stage, tick, max_tokens=64) -> int | None

_ALLOWED_STAGES = {"S1", "S2", "S3", "S4"}
_MAX_CHARS = 300


def _strip_ctrl(s: str) -> str:
    if not s:
        return ""
    # Remove ASCII control chars except newline and tab
    return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]", "", str(s))


def _find_existing(eventlog, rid: int) -> Optional[int]:
    try:
        tail = eventlog.read_tail(limit=400)
    except TypeError:
        tail = eventlog.read_tail(400)  # type: ignore[arg-type]
    except Exception:
        tail = eventlog.read_all()
    for e in reversed(list(tail)):
        if e.get("kind") != "planning_thought":
            continue
        m = e.get("meta") or {}
        if int(m.get("from_event") or 0) == int(rid):
            try:
                return int(e.get("id") or 0)
            except Exception:
                return 0
    return None


def maybe_append_planning_thought(
    eventlog,
    chat: Callable[[str], str],
    *,
    from_reflection_id: int,
    stage: str,
    tick: int,
    max_tokens: int = 64,
) -> Optional[int]:
    """
    Append one privacy-safe planning_thought after a reflection.

    Gates:
    - Stage must be S1+.
    - Single emission per reflection id (meta.from_event).

    chat: callable that takes a prompt and returns a short string.
    This function does not manage budgets; callers should use a budgeted chat wrapper if desired.
    """
    # Stage gate
    if str(stage) not in _ALLOWED_STAGES:
        return None

    rid = int(from_reflection_id)
    # Idempotence: only once per reflection id
    exist = _find_existing(eventlog, rid)
    if exist:
        return exist

    # Fetch reflection content for context (optional)
    reflection_text = ""
    try:
        evs = eventlog.read_all()
        for e in reversed(evs):
            if int(e.get("id") or 0) == rid and e.get("kind") == "reflection":
                reflection_text = str(e.get("content") or "")
                break
    except Exception:
        reflection_text = ""
    # Minimal, privacy-safe prompt (no raw CoT)
    prompt = (
        "You are a self-referential, autonomous, evolving AI. "
        "Output a VERY SHORT plan (max 3 bullets OR <=2 sentences) for how to improve "
        "the next 1–2 replies.\n"
        "Do NOT expose hidden reasoning. No preambles. No explanations.\n"
        "Only actionable steps tied to the latest reflection outcome.\n\n"
        f"Latest reflection:\n{reflection_text}\n"
        "Plan:"
    )

    # Call chat (caller may wrap with budget to emit llm_latency / rate_limit_skip)
    try:
        out = chat(prompt)
    except Exception:
        return None

    if not isinstance(out, str):
        return None

    content = _strip_ctrl(out).strip()
    if not content:
        return None
    if len(content) > _MAX_CHARS:
        content = content[:_MAX_CHARS]

    # Append event
    try:
        eid = eventlog.append(
            kind="planning_thought",
            content=content,
            meta={
                "from_event": rid,
                "tick": int(tick),
                "stage": str(stage),
            },
        )
        return int(eid)
    except Exception:
        return None
