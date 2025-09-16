from __future__ import annotations

from typing import Dict, List, Tuple, Any, Optional
import datetime as _dt
import logging

try:
    from pmm.storage.eventlog import EventLog
except ImportError:
    EventLog = None

logger = logging.getLogger(__name__)

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


class Prioritizer:
    """
    A class to prioritize tasks or commitments based on semantic importance, urgency,
    and other contextual factors within the Persistent Mind Model (PMM).
    """

    def __init__(self, eventlog: Optional["EventLog"] = None):
        self.eventlog = eventlog

    def prioritize_commitments(
        self, commitments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prioritize a list of commitments based on semantic importance and urgency.

        Args:
            commitments: A list of commitment dictionaries with keys like 'cid', 'text', 'status', 'created_at'.

        Returns:
            A sorted list of commitment dictionaries based on priority.
        """
        if not commitments:
            return []

        prioritized = []
        for commitment in commitments:
            priority_score = self._calculate_priority_score(commitment)
            prioritized.append({**commitment, "priority_score": priority_score})

        # Sort by priority score in descending order
        prioritized.sort(key=lambda x: x["priority_score"], reverse=True)

        # Log prioritization results to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="commitments_prioritized",
                content="",
                meta={
                    "commitment_count": len(prioritized),
                    "top_priority": prioritized[0]["cid"] if prioritized else None,
                },
            )

        return prioritized

    def _calculate_priority_score(self, commitment: Dict[str, Any]) -> float:
        """
        Calculate a priority score for a single commitment based on various factors.

        Args:
            commitment: A dictionary representing a commitment.

        Returns:
            A float representing the priority score.
        """
        score = 0.0

        # Base score on status (open commitments have higher priority)
        if commitment.get("status") == "open":
            score += 0.5
        elif commitment.get("status") == "tentative":
            score += 0.3

        # Increase score based on urgency keywords in text (placeholder for semantic analysis)
        text = commitment.get("text", "").lower()
        urgency_keywords = ["urgent", "immediate", "critical", "asap", "soon"]
        for keyword in urgency_keywords:
            if keyword in text:
                score += 0.2

        # Adjust score based on age (older commitments might be less urgent unless critical)
        try:
            from datetime import datetime, timezone

            created_at = datetime.fromisoformat(
                commitment.get("created_at", "").replace("Z", "")
            )
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created_at).days
            # Decrease priority slightly for very old commitments
            if age_days > 30:
                score -= 0.1
        except Exception:
            pass

        return max(0.0, min(1.0, score))

    def filter_high_priority(
        self, commitments: List[Dict[str, Any]], threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Filter commitments to return only those with a priority score above the threshold.

        Args:
            commitments: A list of commitment dictionaries.
            threshold: The minimum priority score for a commitment to be considered high priority.

        Returns:
            A filtered list of high-priority commitment dictionaries.
        """
        prioritized = self.prioritize_commitments(commitments)
        high_priority = [
            c for c in prioritized if c.get("priority_score", 0.0) >= threshold
        ]

        # Log filtering results to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="high_priority_filtered",
                content="",
                meta={
                    "total_commitments": len(commitments),
                    "high_priority_count": len(high_priority),
                    "threshold": threshold,
                },
            )

        return high_priority
