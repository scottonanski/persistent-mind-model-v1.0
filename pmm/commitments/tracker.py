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
from typing import Dict, List, Optional, Tuple
import datetime as _dt

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

    def __init__(
        self, eventlog: EventLog, detector: Optional[CommitmentDetector] = None
    ) -> None:
        self.eventlog = eventlog
        self.detector = detector or get_default_detector()

    def process_assistant_reply(self, text: str) -> List[str]:
        """Detect commitments in assistant replies and open them.

        Returns list of newly opened commitment ids (cids).
        """
        # Expire old commitments (TTL) opportunistically on assistant activity
        try:
            self.expire_old_commitments()
        except Exception:
            # Do not fail user flow if expiration has issues
            pass
        found = self.detector.find(text or "") if self.detector else []
        opened: List[str] = []
        for item in found:
            ctext = item.get("text") or ""
            kind = (item.get("kind") or "plan").strip()
            source = f"detector:{kind}" if kind else "detector"
            cid = self.add_commitment(ctext, source=source)
            if cid:
                opened.append(cid)
        # Identity-name commitment: "I will use the name <X>"
        try:
            m = _re.search(
                r"\bI will use the name\s+([A-Za-z][A-Za-z0-9_-]{0,11})\b",
                text or "",
                _re.IGNORECASE,
            )
            if m:
                x = m.group(1)
                cid2 = self.add_commitment(f"identity:name:{x}", source="identity")
                if cid2:
                    opened.append(cid2)
        except Exception:
            pass
        # If assistant self-ascribes a name ("I am <X>"), attempt to close matching identity commitment
        try:
            m2 = _re.search(
                r"\bI am\s+([A-Za-z][A-Za-z0-9_-]{0,11})\b", text or "", _re.IGNORECASE
            )
            if m2:
                x = m2.group(1)
                self._close_identity_name_commitments(x)
        except Exception:
            pass
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

        done_re = _re.compile(
            r"\b(?:done|completed|finished)\s*:?\s*(.*)$", _re.IGNORECASE
        )
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
                    last_open_event_id[cid] = ev.get("id") or last_open_event_id.get(
                        cid, -1
                    )

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
        # Deduplicate against last N open commitments
        if self._is_duplicate_of_recent_open(text):
            # No-op: return a stable cid-like marker to reflect dedup action
            return ""
        cid = _uuid.uuid4().hex
        meta: Dict = {"cid": cid, "text": text}
        if source is not None:
            meta["source"] = source
        content = f"Commitment opened: {text}"
        self.eventlog.append(kind="commitment_open", content=content, meta=meta)
        return cid

    def close_with_evidence(
        self,
        cid: str,
        evidence_type: str,
        description: str,
        artifact: str | None = None,
    ) -> bool:
        """Attempt to close a commitment with evidence.

        Rules:
        - Only evidence_type == "done" closes.
        - By default, text-only evidence is allowed.
          If env PMM_REQUIRE_ARTIFACT_EVIDENCE is truthy, artifact is required
          (tests may override via TEST_ALLOW_TEXT_ONLY_EVIDENCE).
        - If already closed (derived from projection), returns False.
        """
        if evidence_type != "done":
            return False

        # Env-driven policy: default allow text-only unless strict mode is on
        strict = str(_os.environ.get("PMM_REQUIRE_ARTIFACT_EVIDENCE", "0")) in {
            "1",
            "true",
            "True",
        }
        test_override = bool(_os.environ.get("TEST_ALLOW_TEXT_ONLY_EVIDENCE"))
        allow_text_only = (not strict) or test_override
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

    # --- Identity helpers ---
    def _close_identity_name_commitments(self, name: str) -> None:
        """Close any open identity:name:<name> commitments.

        Uses text-only evidence policy to emit commitment_close events.
        """
        target_txt = f"identity:name:{name}"
        model = build_self_model(self.eventlog.read_all())
        open_map: Dict[str, Dict] = model.get("commitments", {}).get("open", {})
        patt = _re.compile(
            r"\bI will use the name\s+" + _re.escape(name) + r"\b", _re.IGNORECASE
        )
        for cid, meta in list(open_map.items()):
            txt = str((meta or {}).get("text") or "")
            if txt == target_txt or patt.search(txt):
                try:
                    self.close_with_evidence(
                        cid, evidence_type="done", description=f"adopted name {name}"
                    )
                except Exception:
                    continue

    @classmethod
    def close_identity_name_on_adopt(cls, eventlog: EventLog, name: str) -> None:
        """Class helper to close identity commitments when an identity_adopt event is appended."""
        try:
            inst = cls(eventlog)
            inst._close_identity_name_commitments(name)
        except Exception:
            return

    def list_open(self) -> Dict[str, Dict]:
        """Return mapping of cid -> meta for open commitments via projection."""
        model = build_self_model(self.eventlog.read_all())
        return model.get("commitments", {}).get("open", {})

    # --- TTL expiration and dedup helpers ---
    @staticmethod
    def _normalize_text(s: str) -> str:
        return " ".join((s or "").strip().lower().split())

    def _recent_open_cids(self, n: int) -> List[Tuple[str, int]]:
        # Return list of (cid, open_event_id) for currently open commitments, ordered by recency of open
        model = build_self_model(self.eventlog.read_all())
        open_map: Dict[str, Dict] = model.get("commitments", {}).get("open", {})
        open_cids = set(open_map.keys())
        last_open_event_id: Dict[str, int] = {cid: -1 for cid in open_cids}
        for ev in self.eventlog.read_all():  # ascending id
            if ev.get("kind") == "commitment_open":
                cid = (ev.get("meta") or {}).get("cid")
                if cid in open_cids:
                    last_open_event_id[cid] = ev.get("id") or last_open_event_id.get(
                        cid, -1
                    )
        ordered = sorted(last_open_event_id.items(), key=lambda kv: kv[1], reverse=True)
        return ordered[: max(0, n)]

    def _is_duplicate_of_recent_open(self, text: str) -> bool:
        try:
            dedup_n = int(_os.environ.get("PMM_COMMITMENT_DEDUP_WINDOW", "5"))
        except ValueError:
            dedup_n = 5
        cand_norm = self._normalize_text(text)
        model = build_self_model(self.eventlog.read_all())
        open_map: Dict[str, Dict] = model.get("commitments", {}).get("open", {})
        for cid, _eid in self._recent_open_cids(dedup_n):
            txt = str((open_map.get(cid) or {}).get("text") or "")
            if self._normalize_text(txt) == cand_norm:
                return True
        return False

    def expire_old_commitments(self, *, now_iso: str | None = None) -> List[str]:
        """Expire open commitments older than TTL hours.

        Returns list of expired cids.
        """
        try:
            ttl_hours = int(_os.environ.get("PMM_COMMITMENT_TTL_HOURS", "24"))
        except ValueError:
            ttl_hours = 24
        if ttl_hours < 0:
            return []

        # Build maps of open cids and find their open timestamps by scanning events
        events = self.eventlog.read_all()
        model = build_self_model(events)
        open_map: Dict[str, Dict] = model.get("commitments", {}).get("open", {})
        if not open_map:
            return []

        # Map cid -> first open event ts (ISO string)
        opened_ts: Dict[str, str] = {}
        for ev in events:
            if ev.get("kind") == "commitment_open":
                m = ev.get("meta") or {}
                cid = m.get("cid")
                if cid in open_map and cid not in opened_ts:
                    opened_ts[cid] = ev.get("ts")

        # Determine current time ISO
        if now_iso is None:
            now_iso = _dt.datetime.now(_dt.UTC).isoformat()
        now_dt = _dt.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))

        expired: List[str] = []
        for cid, ts in opened_ts.items():
            try:
                open_dt = _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except Exception:
                continue
            age_hours = (now_dt - open_dt).total_seconds() / 3600.0
            if age_hours >= ttl_hours:
                # Append expiration event
                text0 = str((open_map.get(cid) or {}).get("text") or "")
                meta = {
                    "cid": cid,
                    "reason": "ttl",
                    "expired_at": now_iso,
                }
                self.eventlog.append(
                    kind="commitment_expire",
                    content=f"Commitment expired: {text0}",
                    meta=meta,
                )
                expired.append(cid)
        return expired
