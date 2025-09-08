"""Minimal commitment tracking built on EventLog + projection.

Intent:
- Evidence-first lifecycle only: open via explicit user/agent action,
  close only with allowed evidence.
- No TTL, no heuristics, no autoclose.
"""

from __future__ import annotations

import os as _os
import uuid as _uuid
from typing import Dict

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model


class CommitmentTracker:
    """Commitment lifecycle backed by the EventLog.

    Parameters
    ----------
    eventlog : EventLog
        The event log instance to persist events into.
    """

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog

    def add_commitment(self, text: str, source: str | None = None) -> str:
        """Open a new commitment and return its cid.

        Logs: kind="commitment_open" with meta {"cid", "text", "source"}.
        """
        cid = _uuid.uuid4().hex
        meta: Dict = {"cid": cid, "text": text}
        if source is not None:
            meta["source"] = source
        content = f"Commitment opened: {text}"
        self.eventlog.append(kind="commitment_open", content=content, meta=meta)
        return cid

    def close_with_evidence(
        self, cid: str, evidence_type: str, description: str, artifact: str | None = None
    ) -> bool:
        """Attempt to close a commitment with evidence.

        Rules:
        - Only evidence_type == "done" closes.
        - artifact is required unless env TEST_ALLOW_TEXT_ONLY_EVIDENCE is truthy.
        - If already closed (derived from projection), returns False.
        """
        if evidence_type != "done":
            return False

        allow_text_only = bool(_os.environ.get("TEST_ALLOW_TEXT_ONLY_EVIDENCE"))
        if not artifact and not allow_text_only:
            return False

        # Derive open commitments from projection
        model = build_self_model(self.eventlog.read_all())
        open_map: Dict[str, Dict] = model.get("commitments", {}).get("open", {})
        if cid not in open_map:
            # Unknown or already closed
            return False

        meta: Dict = {
            "cid": cid,
            "evidence_type": evidence_type,
            "description": description,
        }
        if artifact is not None:
            meta["artifact"] = artifact

        content = f"Commitment closed: {cid}"
        self.eventlog.append(kind="commitment_close", content=content, meta=meta)
        return True

    def list_open(self) -> Dict[str, Dict]:
        """Return mapping of cid -> meta for open commitments via projection."""
        model = build_self_model(self.eventlog.read_all())
        return model.get("commitments", {}).get("open", {})

