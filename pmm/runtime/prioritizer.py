from __future__ import annotations

from typing import Dict, List, Tuple
import datetime as _dt


W1_URGENCY = 0.6
W2_NOVELTY = 0.3
W3_AGE_PENALTY = 0.1


def _parse_ts(ts: str | None) -> _dt.datetime | None:
    if not ts:
        return None
    try:
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _token_set(s: str) -> set[str]:
    import re

    s = (s or "").lower()
    tokens = re.findall(r"[a-z0-9']+", s)
    return set(tokens)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def rank_commitments(events: List[Dict]) -> List[Tuple[str, float]]:
    """Compute a ranking of open commitments by score.

    Score = 0.6*urgency + 0.3*novelty_gain + 0.1*age_penalty
      - urgency: age_hours / ttl_hours (clamped [0,1])
      - novelty_gain: 1.0 if dissimilar to last 5 assistant replies (Jaccard < 0.3), else 0.2
      - age_penalty: -0.2 if age > 24h else 0.0
    Returns list of (cid, score) sorted descending by score, tie-broken by opened ts then cid.
    """
    # Gather open commitments map and their open timestamps
    open_map: Dict[str, Dict] = {}
    opened_ts: Dict[str, _dt.datetime] = {}
    for ev in events:
        if ev.get("kind") == "commitment_open":
            meta = ev.get("meta") or {}
            cid = meta.get("cid")
            if cid:
                open_map[cid] = meta
                opened_ts[cid] = _parse_ts(ev.get("ts")) or _dt.datetime.now(_dt.UTC)
        elif ev.get("kind") in ("commitment_close", "commitment_expire"):
            meta = ev.get("meta") or {}
            cid = meta.get("cid")
            if cid and cid in open_map:
                # Closed, remove from consideration
                open_map.pop(cid, None)
                opened_ts.pop(cid, None)

    # Get last 5 assistant replies
    replies: List[str] = [
        ev.get("content") or "" for ev in events if ev.get("kind") == "response"
    ]
    tail = replies[-5:]
    tail_sets = [_token_set(t) for t in tail]

    now = _dt.datetime.now(_dt.UTC)
    # TTL in hours (use default 24 if no env layer here)
    ttl_hours = 24.0

    scored: List[Tuple[str, float]] = []
    for cid, meta in open_map.items():
        text = str(meta.get("text") or "")
        t_open = opened_ts.get(cid) or now
        age_hours = max(0.0, (now - t_open).total_seconds() / 3600.0)

        urgency = max(0.0, min(1.0, age_hours / ttl_hours))

        cset = _token_set(text)
        max_sim = 0.0
        for s in tail_sets:
            max_sim = max(max_sim, _jaccard(cset, s))
        novelty_gain = 1.0 if max_sim < 0.3 else 0.2

        age_penalty = -0.2 if age_hours > 24.0 else 0.0

        score = (
            W1_URGENCY * urgency
            + W2_NOVELTY * novelty_gain
            + W3_AGE_PENALTY * age_penalty
        )
        scored.append((cid, float(score)))

    # Sort: score desc, then opened_ts asc (older first), then cid asc
    scored.sort(key=lambda x: (-x[1], opened_ts.get(x[0]) or now, x[0]))
    return scored
