"""Commitment manager for opening/closing commitments (minimal)."""

from __future__ import annotations

from hashlib import sha1
from typing import Optional

from pmm_v2.core.event_log import EventLog


class CommitmentManager:
    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog

    def _derive_cid(self, text: str) -> str:
        return sha1(text.encode("utf-8")).hexdigest()[:8]

    def open_commitment(self, text: str, source: str = "assistant") -> str:
        text = (text or "").strip()
        if not text:
            return ""
        cid = self._derive_cid(text)
        self.eventlog.append(
            kind="commitment_open",
            content=f"Commitment opened: {text}",
            meta={"cid": cid, "text": text, "source": source},
        )
        return cid

    def open_internal(self, goal: str, reason: str) -> str:
        text = f"INTERNAL_GOAL: {goal}"
        if reason:
            text += f" | {reason}"
        cid = f"mc_{self._derive_cid(text)}"
        self.eventlog.append(
            kind="commitment_open",
            content=f"Commitment opened: {text}",
            meta={
                "cid": cid,
                "goal": goal,
                "reason": reason,
                "source": "autonomy_kernel",
            },
        )
        return cid

    def close_commitment(self, cid: str, source: str = "assistant") -> Optional[int]:
        if not cid:
            return None
        return self.eventlog.append(
            kind="commitment_close",
            content=f"Commitment closed: {cid}",
            meta={"cid": cid, "source": source},
        )

    def apply_closures(self, cids: list[str], source: str = "assistant") -> list[str]:
        """Close only those commitments currently open; idempotent.

        Returns list of cids that were actually closed.
        """
        from pmm_v2.core.ledger_mirror import LedgerMirror

        mirror = LedgerMirror(self.eventlog)
        closed: list[str] = []
        for cid in cids:
            if mirror.is_commitment_open(cid):
                self.close_commitment(cid, source=source)
                closed.append(cid)
        return closed
