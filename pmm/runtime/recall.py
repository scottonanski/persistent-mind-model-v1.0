from __future__ import annotations

_STOP = {
    "i",
    "we",
    "you",
    "the",
    "a",
    "an",
    "to",
    "and",
    "of",
    "for",
    "on",
    "in",
    "it",
    "is",
    "are",
    "will",
    "shall",
    "can",
    "could",
    "should",
    "would",
    "today",
    "now",
}


def _tokens(s: str) -> list[str]:
    from pmm.utils.parsers import split_non_alnum

    toks = [t for t in split_non_alnum(s or "") if t and t not in _STOP]
    return toks


def _score_overlap(src_toks: list[str], tgt_toks: list[str]) -> int:
    if not src_toks or not tgt_toks:
        return 0
    st = set(src_toks)
    return sum(1 for t in tgt_toks if t in st)


def suggest_recall(
    events: list[dict],
    current_text: str,
    *,
    max_items: int = 3,
    semantic_seeds: list[int] | None = None,
) -> list[dict]:
    """
    Deterministic recall suggestions based on token overlap.

    - Score by token overlap between `current_text` and prior event content/commitment text.
    - Consider prior events only (exclude the last event if equal content).
    - Tie-break by smaller eid (earlier event stronger for stability).
    - Return up to `max_items` items as dicts: {"eid": int, "snippet": str}.
    """
    curr = _tokens(current_text)

    # First pass: build quick candidates scored by token overlap only
    quick_candidates: list[tuple[float, int, str, str]] = (
        []
    )  # (overlap_score, eid, snippet, tgt_text)
    # Identify latest event id to ensure we only reference prior events
    latest_id = 0
    for ev in events:
        try:
            eid_tmp = int(ev.get("id") or 0)
        except Exception:
            eid_tmp = 0
        if eid_tmp > latest_id:
            latest_id = eid_tmp

    # Build candidate set: prefer commitment_open content; fallback to any event with meaningful content
    for ev in events:
        try:
            eid = int(ev.get("id") or 0)
        except Exception:
            continue
        # exclude the latest event (assumed to be the current reply just appended by runtime)
        if eid >= latest_id:
            continue
        kind = ev.get("kind")
        content = str(ev.get("content") or "")
        # Skip trivial events
        if not content:
            continue
        # Compute target tokens: for commitment_open, include meta.text if available
        tgt_text = content
        if kind == "commitment_open":
            meta = ev.get("meta") or {}
            txt = meta.get("text")
            if isinstance(txt, str) and txt:
                tgt_text = f"{content}\n{txt}"
        tgt_toks = _tokens(tgt_text)
        # If semantic seeds provided, restrict to those eids
        if semantic_seeds is not None:
            try:
                seed_set: set[int] = set(int(x) for x in semantic_seeds)
            except Exception:
                seed_set = set()
            if eid not in seed_set:
                # skip non-seeded items in semantic mode
                continue
        # Fast token-overlap score
        ov = float(_score_overlap(curr, tgt_toks))
        if ov <= 0.0:
            continue
        # Snippet: bounded to 100 chars from event content
        snippet = content[:100]
        quick_candidates.append((ov, eid, snippet, tgt_text))

    # Prefilter: keep only top-K by overlap to bound embedding calls
    top_k = max(max_items, 10)
    quick_candidates.sort(key=lambda t: (-float(t[0]), t[1]))
    prefiltered = quick_candidates[:top_k]

    # Second pass (optional legacy): refine scores with embeddings for prefiltered items if available
    scored: list[tuple[float, int, str]] = []  # (score, eid, snippet)
    for ov, eid, snippet, _t in prefiltered:
        scored.append((ov, eid, snippet))

    # Sort by score desc, then eid asc, then truncate to max_items
    out: list[dict] = []
    used = set()
    scored.sort(key=lambda t: (-float(t[0]), t[1]))
    for sc, eid, snip in scored:
        if eid in used:
            continue
        used.add(eid)
        out.append({"eid": eid, "snippet": snip})
        if len(out) >= max_items:
            break
    return out
