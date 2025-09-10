from __future__ import annotations

from typing import List, Dict, Tuple
import re as _re
from pmm.runtime.embeddings import compute_embedding, cosine_similarity
import os as _os

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
    # Determine if we should use embeddings: require enable flag AND either test/dummy mode or OPENAI_API_KEY present
    enabled = str(_os.environ.get("PMM_EMBEDDINGS_ENABLE", "1")).lower() in {
        "1",
        "true",
        "True",
    }
    test_mode = any(
        str(_os.environ.get(k, "0")).lower() in {"1", "true"}
        for k in ("PMM_EMBEDDINGS_DUMMY", "TEST_EMBEDDINGS", "TEST_EMBEDDINGS_CONSTANT")
    )
    has_key = bool(_os.environ.get("OPENAI_API_KEY"))
    use_embeddings = enabled and (test_mode or has_key)
    # Compute embedding for current_text once (if allowed)
    emb_curr = compute_embedding(current_text) if use_embeddings else None
    # Tiny per-call cache to avoid duplicate compute cost for repeated texts
    _emb_cache: Dict[str, List[float] | None] = {}

    def _emb(text: str):
        if text not in _emb_cache:
            _emb_cache[text] = compute_embedding(text)
        return _emb_cache[text]

    # First pass: build quick candidates scored by token overlap only
    quick_candidates: List[Tuple[float, int, str, str]] = (
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
        # Fast token-overlap score
        ov = float(_score_overlap(curr, tgt_toks))
        if ov <= 0.0:
            continue
        # Snippet: bounded to 100 chars from event content
        snippet = content[:100]
        quick_candidates.append((ov, eid, snippet, tgt_text))

    # Prefilter: keep only top-K by overlap to bound embedding calls
    TOP_K = max(max_items, 10)
    quick_candidates.sort(key=lambda t: (-float(t[0]), t[1]))
    prefiltered = quick_candidates[:TOP_K]

    # Second pass (optional): refine scores with embeddings for prefiltered items
    scored: List[Tuple[float, int, str]] = []  # (score, eid, snippet)
    if emb_curr is not None and use_embeddings:
        for ov, eid, snippet, tgt_text in prefiltered:
            emb_tgt = _emb(tgt_text)
            if emb_tgt is not None:
                sc = cosine_similarity(emb_curr, emb_tgt)
                # Combine: prefer cosine; ensure we never do worse than overlap
                sc = max(sc, ov)
            else:
                sc = ov
            scored.append((sc, eid, snippet))
    else:
        # No embeddings: use the overlap-only prefiltered set
        for ov, eid, snippet, _t in prefiltered:
            scored.append((ov, eid, snippet))

    # Sort by score desc, then eid asc, then truncate to max_items
    out: List[Dict] = []
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
