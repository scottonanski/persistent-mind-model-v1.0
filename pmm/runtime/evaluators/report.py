from __future__ import annotations

from collections.abc import Callable

_MAX_CHARS = 300


def _strip_ctrl(s: str) -> str:
    if not s:
        return ""
    # Remove ASCII control chars except newline and tab (deterministic)
    result = []
    for char in str(s):
        code = ord(char)
        # Keep newline (0x0A) and tab (0x09), skip other control chars
        if code == 0x0A or code == 0x09 or (code >= 0x20 and code != 0x7F):
            result.append(char)
    return "".join(result)


def _find_existing_summary(eventlog, report_id: int) -> int | None:
    try:
        tail = eventlog.read_tail(limit=400)
    except TypeError:
        tail = eventlog.read_tail(400)  # type: ignore[arg-type]
    except Exception:
        tail = eventlog.read_all()
    for e in reversed(list(tail)):
        if e.get("kind") != "evaluation_summary":
            continue
        m = e.get("meta") or {}
        if int(m.get("from_report_id") or 0) == int(report_id):
            try:
                return int(e.get("id") or 0)
            except Exception:
                return 0
    return None


def maybe_emit_evaluation_summary(
    eventlog,
    chat: Callable[[str], str],
    *,
    from_report_id: int,
    stage: str,
    tick: int,
    max_tokens: int = 64,
) -> int | None:
    """
    After an evaluation_report, emit a short evaluation_summary once per report.

    Idempotent per from_report_id. Uses provided `chat` to produce a tiny summary.
    """
    rid = int(from_report_id)
    exist = _find_existing_summary(eventlog, rid)
    if exist:
        return exist

    # Load the referenced report for metrics context (optional)
    metrics = {}
    try:
        evs = eventlog.read_all()
        for e in reversed(evs):
            if int(e.get("id") or 0) == rid and e.get("kind") == "evaluation_report":
                metrics = (e.get("meta") or {}).get("metrics") or {}
                break
    except Exception:
        metrics = {}

    # Minimal prompt guiding a concise summary
    prompt = (
        "Summarize these metrics very briefly (<=2 sentences).\n"
        "Do NOT reveal hidden reasoning, only a concise operator-facing summary.\n"
        f"Metrics: {metrics}\n"
        "Summary:"
    )

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

    try:
        eid = eventlog.append(
            kind="evaluation_summary",
            content=content,
            meta={
                "from_report_id": rid,
                "tick": int(tick),
                "stage": str(stage),
            },
        )
        return int(eid)
    except Exception:
        return None
