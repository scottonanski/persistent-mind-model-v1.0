from __future__ import annotations


def _tokens(s: str) -> list[str]:
    from pmm.utils.parsers import normalize_whitespace

    # We don't lowercase to preserve readability in snippet summaries; but we do trim
    return normalize_whitespace(s or "").split()


def _summarize_chunk(evts: list[dict], *, max_chars: int = 500) -> str:
    """
    Deterministic compaction:
    - Take up to the first 6 and last 6 non-empty event contents from the window.
    - For each, include `[{kind} #{id}]` and up to first 14 tokens of content.
    - Join with " \n" and truncate to max_chars.
    """
    lines: list[str] = []
    # Filter events with some content
    candidates = [e for e in evts if str(e.get("content") or "").strip()]
    head = candidates[:6]
    tail = candidates[-6:] if len(candidates) > 6 else []
    seq = head + (tail if tail and tail[0] is not head[-1] else tail)
    for e in seq:
        kind = str(e.get("kind") or "")
        eid = int(e.get("id") or 0)
        content = str(e.get("content") or "").strip()
        toks = _tokens(content)[:14]
        text = " ".join(toks)
        lines.append(f"[{kind} #{eid}] {text}")
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars]
    return out


def _last_compact_window(events: list[dict]) -> dict | None:
    for ev in reversed(events):
        if ev.get("kind") == "scene_compact":
            m = ev.get("meta") or {}
            win = m.get("window") or {}
            try:
                start = int((win or {}).get("start") or 0)
                end = int((win or {}).get("end") or 0)
            except Exception:
                start, end = 0, 0
            return {"start": start, "end": end}
    return None


def maybe_compact(events: list[dict], *, threshold: int = 100) -> dict | None:
    """
    If events since last compaction >= threshold, return a summary dict with shape:
    {"content": str, "source_ids": [...], "window": {"start": int, "end": int}}
    Otherwise return None. Deterministic, no randomness.
    """
    if not events:
        return None
    # Determine last compact window end
    last_win = _last_compact_window(events)
    last_end = int(last_win.get("end") or 0) if last_win else 0
    # Collect new events strictly after last_end
    newer = [e for e in events if int(e.get("id") or 0) > last_end]
    if len(newer) < threshold:
        return None
    # Build window using the last `threshold` events to avoid overlap and keep fixed-size scenes
    newer_sorted = sorted(newer, key=lambda e: int(e.get("id") or 0))
    tail = newer_sorted[-threshold:]
    source_ids = [int(e.get("id") or 0) for e in tail]
    start = source_ids[0]
    end = source_ids[-1]
    # Compose deterministic summary from these events (bounded length)
    content = _summarize_chunk(
        [e for e in events if start <= int(e.get("id") or 0) <= end], max_chars=500
    )
    return {
        "content": content,
        "source_ids": source_ids,
        "window": {"start": start, "end": end},
    }
