from __future__ import annotations

from typing import List, Dict
import re as _re
from pmm.runtime.embeddings import compute_embedding, cosine_similarity

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


def _tokens(s: str) -> List[str]:
    s2 = _re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    toks = [t for t in s2.split() if t and t not in _STOP]
    return toks


def _score_overlap(src_toks: List[str], tgt_toks: List[str]) -> int:
    if not src_toks or not tgt_toks:
        return 0
    st = set(src_toks)
    return sum(1 for t in tgt_toks if t in st)


def suggest_recall(
    events: List[Dict], current_text: str, *, max_items: int = 3
) -> List[Dict]:
    """
    Deterministic recall suggestions based on token overlap.

    - Score by token overlap between `current_text` and prior event content/commitment text.
    - Consider prior events only (exclude the last event if equal content).
    - Tie-break by smaller eid (earlier event stronger for stability).
    - Return up to `max_items` items as dicts: {"eid": int, "snippet": str}.
    """
    curr = _tokens(current_text)
    # Compute embedding for current_text once (if provider present)
    emb_curr = compute_embedding(current_text)
    scored: List[tuple[int, int, str]] = []  # (score, eid_for_tie, snippet)
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
        # Prefer embeddings if available; else use token overlap
        sc = 0.0
        if emb_curr is not None:
            emb_tgt = compute_embedding(tgt_text)
            if emb_tgt is not None:
                sc = cosine_similarity(emb_curr, emb_tgt)
        if sc == 0.0:
            sc = float(_score_overlap(curr, tgt_toks))
        if sc <= 0.0:
            continue
        # Snippet: bounded to 100 chars from event content
        snippet = content[:100]
        scored.append((sc, eid, snippet))

    # Sort by score desc, then eid asc (because we stored -eid), then truncate
    scored.sort(key=lambda t: (-float(t[0]), t[1]))

    out: List[Dict] = []
    used = set()
    for sc, eid, snip in scored:
        if eid in used:
            continue
        used.add(eid)
        out.append({"eid": eid, "snippet": snip})
        if len(out) >= max_items:
            break
    return out
