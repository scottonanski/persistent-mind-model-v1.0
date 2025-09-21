from __future__ import annotations

from typing import Tuple, Dict, Any, List, Optional

# Pure, deterministic acceptance gate for reflections.
# No I/O, no randomness, no external dependencies. Operates only on provided inputs.
#
# API:
#   accept(text, events, stage, opts) -> (accepted: bool, reason: str, meta: dict)
#
# Gates (short-circuit order):
#   1) Text hygiene (min/max chars, min lines)
#   2) Local n-gram dedup vs last N reflections (ngram_len=3)
#   3) Optional embedding duplicate (EXACT digest match only) — disabled by default; this
#      function does not compute embeddings by itself. If ever enabled, the caller must
#      provide a candidate digest via opts["embedding_gate"]["candidate_digest"].
#   4) Bootstrap accept (one-shot) when no accepted reflections for T ticks or rejection
#      streak of K since last acceptance.
#
# All thresholds are configurable via opts; sensible defaults are provided below.

DEFAULTS = {
    "min_chars": 30,
    "max_chars": 1200,
    "min_lines": 2,
    "ngram_len": 3,
    "ngram_window": 10,
    # Stage thresholds keyed by integer level (0..4) and -1 for UNKNOWN/default
    "stage_thresholds": {
        0: 0.75,
        1: 0.65,
        2: 0.55,
        3: 0.45,
        4: 0.40,
        -1: 0.60,
    },
    "bootstrap": {"ticks": 8, "streak": 3},
    "embedding_gate": {"enabled": False, "candidate_digest": None, "window": 20},
    # Add stricter quality checks to prevent empty reflections
    "min_meaningful_chars": 50,  # Minimum characters with meaningful content
    "max_repetitive_ratio": 0.8,  # Maximum ratio of repetitive content
}


def _get(events: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    return [e for e in events if e.get("kind") == key]


def _recent_reflections(events: List[Dict[str, Any]], window: int) -> List[str]:
    out: List[str] = []
    for e in reversed(events):
        if e.get("kind") == "reflection":
            out.append(str(e.get("content") or ""))
            if len(out) >= window:
                break
    return list(reversed(out))


def _tokenize(text: str) -> List[str]:
    return [t for t in str(text or "").lower().split() if t]


def _ngrams(tokens: List[str], n: int) -> List[tuple]:
    if n <= 0:
        return []
    return [tuple(tokens[i : i + n]) for i in range(0, max(0, len(tokens) - n + 1))]


def _overlap_ratio(a: List[tuple], b: List[tuple]) -> float:
    if not a:
        return 0.0
    sa = set(a)
    sb = set(b)
    inter = sa.intersection(sb)
    return float(len(inter)) / float(max(1, len(sa)))


def _last_reflection_id(events: List[Dict[str, Any]]) -> Optional[int]:
    for e in reversed(events):
        if e.get("kind") == "reflection":
            try:
                return int(e.get("id") or 0)
            except Exception:
                return 0
    return None


def _ticks_since(events: List[Dict[str, Any]], since_id: Optional[int]) -> int:
    if since_id is None:
        # No reflection at all -> treat as infinite ticks since
        return 10**6
    cnt = 0
    for e in reversed(events):
        try:
            eid = int(e.get("id") or 0)
        except Exception:
            continue
        if eid <= since_id:
            break
        if e.get("kind") == "autonomy_tick":
            cnt += 1
    return cnt


def _rejection_streak_since(
    events: List[Dict[str, Any]], since_id: Optional[int]
) -> int:
    cnt = 0
    for e in reversed(events):
        try:
            eid = int(e.get("id") or 0)
        except Exception:
            continue
        if since_id is not None and eid <= since_id:
            break
        if e.get("kind") == "debug":
            meta = e.get("meta") or {}
            if "reflection_reject" in meta:
                cnt += 1
            else:
                # unrelated debug breaks consecutive streak counting
                break
        elif e.get("kind") in {"reflection", "autonomy_tick"}:
            # keep scanning past autonomy_tick; reflection indicates acceptance boundary
            continue
        else:
            # non-related event -> stop strict consecutive count
            break
    return cnt


def accept(
    text: str,
    events: List[Dict[str, Any]],
    stage_level: Optional[int],
    opts: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Deterministic reflection acceptance gate.

    Returns (accepted, reason, meta) where meta includes scoring/threshold telemetry.
    """
    cfg = {**DEFAULTS}
    if opts:
        # shallow merge for top-level keys and nested maps we know about
        for k in ("stage_thresholds", "bootstrap", "embedding_gate"):
            if k in opts and isinstance(opts[k], dict):
                cfg[k] = {**cfg[k], **opts[k]}
        for k in ("min_chars", "max_chars", "min_lines", "ngram_len", "ngram_window"):
            if k in opts:
                cfg[k] = opts[k]

    # 1) Text hygiene
    t = str(text or "")
    lines = [ln for ln in t.splitlines() if ln.strip()]
    len_chars = len(t)
    len_lines = len(lines)
    if len_chars < int(cfg["min_chars"]):
        return (False, "too_short", {"len_chars": len_chars, "len_lines": len_lines})
    if len_chars > int(cfg["max_chars"]):
        return (False, "too_long", {"len_chars": len_chars, "len_lines": len_lines})
    if len_lines < int(cfg["min_lines"]):
        return (
            False,
            "too_few_lines",
            {"len_chars": len_chars, "len_lines": len_lines},
        )

    # 2) Quality checks - prevent empty and repetitive reflections
    t_lower = t.lower()
    # Calculate quality score based on meaningful content
    meaningful_chars = len([c for c in t if c.isalnum() or c in " .,!?-"])
    quality_score = meaningful_chars / max(1, len_chars)

    # Check for repetitive content patterns
    words = t_lower.split()
    if len(words) > 3:
        unique_words = set(words)
        repetitive_ratio = (len(words) - len(unique_words)) / len(words)
        if repetitive_ratio > float(cfg.get("max_repetitive_ratio", 0.8)):
            return (
                False,
                "too_repetitive",
                {
                    "quality_score": round(quality_score, 3),
                    "repetitive_ratio": round(repetitive_ratio, 3),
                    "len_chars": len_chars,
                    "len_lines": len_lines,
                },
            )

    # Check for policy adjustment loops
    policy_keywords = ["novelty_threshold", "policy:", "lower", "increase", "decrease"]
    policy_count = sum(1 for kw in policy_keywords if kw in t_lower)
    # Trigger if too many policy keywords regardless of quality (prevents policy spam)
    if policy_count >= 3:
        return (
            False,
            "policy_loop_detected",
            {
                "quality_score": round(quality_score, 3),
                "policy_keywords": policy_count,
                "len_chars": len_chars,
                "len_lines": len_lines,
            },
        )

    # 3) N-gram dedup vs last N reflections
    window = int(cfg["ngram_window"]) or 10
    n = int(cfg["ngram_len"]) or 3
    recent = _recent_reflections(events, window)
    cand_tokens = _tokenize(t)
    cand_ngrams = _ngrams(cand_tokens, n)
    max_overlap = 0.0
    for prev in recent:
        prev_tokens = _tokenize(prev)
        prev_ngrams = _ngrams(prev_tokens, n)
        max_overlap = max(max_overlap, _overlap_ratio(cand_ngrams, prev_ngrams))
    thresholds = cfg["stage_thresholds"]
    lvl = -1 if stage_level is None else int(stage_level)
    thr = float(thresholds.get(lvl, thresholds.get(-1, 0.60)))
    if max_overlap >= thr:
        return (
            False,
            "ngram_duplicate",
            {
                "ngram_overlap": round(max_overlap, 3),
                "threshold": thr,
                "stage_level": lvl,
            },
        )

    # 4) Optional embedding duplicate (exact digest)
    emb_cfg = cfg["embedding_gate"] or {}
    if emb_cfg.get("enabled"):
        cand_digest = emb_cfg.get("candidate_digest")
        if cand_digest:
            # scan the last M reflections for a matching embedding_indexed digest
            m = int(emb_cfg.get("window", 20))
            # build set of digests associated with last M reflections
            digests: set[str] = set()
            # map reflection id -> digest events following it
            # since events are append-only, collect all embedding_indexed digests
            for e in reversed(events):
                if e.get("kind") == "embedding_indexed":
                    md = e.get("meta") or {}
                    d = md.get("digest")
                    if d:
                        digests.add(str(d))
                if len(digests) >= m:
                    break
            if str(cand_digest) in digests:
                return (False, "embedding_duplicate", {"embedding_match": True})

    # 5) Bootstrap accept (only after hygiene; may bypass dedup/embedding)
    # BUT NOT if quality is too low - prevent empty reflections from ever passing
    last_ref_id = _last_reflection_id(events)
    tick_gap = _ticks_since(events, last_ref_id)
    rej_streak = _rejection_streak_since(events, last_ref_id)

    # Only allow bootstrap if quality meets minimum threshold
    if quality_score >= 0.3 and (
        (tick_gap >= int(cfg["bootstrap"]["ticks"]))
        or (rej_streak >= int(cfg["bootstrap"]["streak"]))
    ):
        return (
            True,
            "bootstrap_accept",
            {
                "ticks_since": tick_gap,
                "rejection_streak": rej_streak,
                "quality_score": round(quality_score, 3),
            },
        )

    # passed all gates
    return (
        True,
        "ok",
        {
            "ngram_overlap": round(max_overlap, 3),
            "threshold": thr,
            "stage_level": lvl,
            "len_chars": len_chars,
            "len_lines": len_lines,
            "quality_score": round(quality_score, 3),
        },
    )
