"""Minimal commitment tracking built on EventLog + projection.

Intent:
- Evidence-first lifecycle only: open via explicit user/agent action,
  close only with allowed evidence.
- No TTL, no heuristics, no autoclose.
"""

from __future__ import annotations

import os as _os
import uuid as _uuid
import re as _re
from typing import Dict, List, Optional

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.commitments.detectors import CommitmentDetector, get_default_detector


class CommitmentTracker:
    """Commitment lifecycle backed by the EventLog.

    Parameters
    ----------
    eventlog : EventLog
        The event log instance to persist events into.
    detector : CommitmentDetector | None
        Optional detector used to extract commitments from assistant text.
    """

    def __init__(self, eventlog: EventLog, detector: Optional[CommitmentDetector] = None) -> None:
        self.eventlog = eventlog
        self.detector = detector or get_default_detector()

    def process_assistant_reply(self, text: str) -> List[str]:
        """Detect commitments in assistant replies and open them.

        Returns list of newly opened commitment ids (cids).
        """
        found = self.detector.find(text or "") if self.detector else []
        opened: List[str] = []
        for item in found:
            ctext = item.get("text") or ""
            kind = (item.get("kind") or "plan").strip()
            source = f"detector:{kind}" if kind else "detector"
            cid = self.add_commitment(ctext, source=source)
            opened.append(cid)
        return opened

    def process_evidence(self, text: str) -> List[str]:
        """Detect "Done:" style evidence and close matching commitments.

        Strategy:
        - Parse for tokens like Done/Completed/Finished (case-insensitive) with optional details.
        - If details substring-match an open commitment text, close the most recently opened among matches.
        - Else, close the most recently opened commitment among all open ones.
        Returns list of closed cids (0 or 1 element currently).
        """
        if not text:
            return []

        done_re = _re.compile(r"\b(?:done|completed|finished)\s*:?\s*(.*)$", _re.IGNORECASE)
        m = done_re.search(text)
        if not m:
            return []

        detail = (m.group(1) or "").strip().lower()

        # Gather open commitments map
        model = build_self_model(self.eventlog.read_all())
        open_map: Dict[str, Dict] = model.get("commitments", {}).get("open", {})
        if not open_map:
            return []

        open_cids = set(open_map.keys())

        # Determine last open event id per cid to rank recency
        last_open_event_id: Dict[str, int] = {cid: -1 for cid in open_cids}
        for ev in self.eventlog.read_all():  # ascending id
            if ev.get("kind") == "commitment_open":
                cid = (ev.get("meta") or {}).get("cid")
                if cid in open_cids:
                    last_open_event_id[cid] = ev.get("id") or last_open_event_id.get(cid, -1)

        # Candidates filtered by substring detail (if provided)
        candidates = list(open_cids)
        if detail:
            matches = []
            for cid in open_cids:
                text0 = str((open_map.get(cid) or {}).get("text") or "").lower()
                if detail and detail in text0:
                    matches.append(cid)
            if matches:
                candidates = matches

        # Pick most recently opened among candidates
        target_cid = None
        if candidates:
            target_cid = max(candidates, key=lambda c: last_open_event_id.get(c, -1))

        if not target_cid:
            return []

        ok = self.close_with_evidence(
            target_cid,
            evidence_type="done",
            description=text,
            artifact=None,
        )
        return [target_cid] if ok else []

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

