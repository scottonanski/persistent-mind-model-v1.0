from __future__ import annotations

from typing import Any, Dict, List

from pmm.core.event_log import EventLog
from pmm.core.ledger_mirror import LedgerMirror
from pmm.core.commitment_manager import CommitmentManager


def build_context(eventlog: EventLog, limit: int = 5) -> str:
    """Deterministically reconstruct a short context window from the ledger.

    Includes only user/assistant messages, capped to the last `limit` pairs.
    """
    # Over-fetch recent events and then filter to message kinds
    rows = list(eventlog.read_tail(limit * 8))
    lines: List[str] = []
    for e in rows:
        kind = e.get("kind")
        if kind in ("user_message", "assistant_message"):
            lines.append(f"{kind}: {e.get('content','')}")
    tail = lines[-(limit * 2) :]
    body = "\n".join(tail)

    mirror = LedgerMirror(eventlog, listen=False)
    snapshot = mirror.rsm_snapshot()
    rsm_block = _render_rsm(snapshot)
    goals_block = _render_internal_goals(eventlog)

    extras = "\n".join(section for section in (rsm_block, goals_block) if section)
    if body and extras:
        return f"{body}\n\n{extras}"
    if extras:
        return extras
    return body


def _render_rsm(snapshot: Dict[str, Any]) -> str:
    if not snapshot:
        return ""
    tendencies = snapshot.get("behavioral_tendencies") or {}
    gaps = snapshot.get("knowledge_gaps") or []
    meta_patterns = snapshot.get("interaction_meta_patterns") or []
    # If uniqueness is the only tendency and no other signals, hide RSM block
    nonzero_tendencies = {k: v for k, v in tendencies.items() if v}
    if (
        nonzero_tendencies.keys() == {"uniqueness_emphasis"}
        and not gaps
        and not meta_patterns
    ):
        return ""
    if not (tendencies or gaps or meta_patterns):
        return ""

    tendency_parts = [f"{key} ({tendencies[key]})" for key in sorted(tendencies.keys())]
    gaps_part = ", ".join(gaps)
    tendencies_text = ", ".join(tendency_parts) if tendency_parts else "none"
    gaps_text = gaps_part if gaps_part else "none"
    lines = [
        "Recursive Self-Model:",
        f"- Tendencies: {tendencies_text}",
        f"- Gaps: {gaps_text}",
    ]
    return "\n".join(lines)


def _render_internal_goals(eventlog: EventLog) -> str:
    manager = CommitmentManager(eventlog)
    open_internal = manager.get_open_commitments(origin="autonomy_kernel")
    parts: List[str] = []
    for event in open_internal:
        meta = event.get("meta") or {}
        cid = meta.get("cid")
        goal = meta.get("goal") or "unknown"
        if not cid:
            continue
        parts.append(f"{cid} ({goal})")
    if not parts:
        return ""
    return f"Internal Goals: {', '.join(parts)}"
