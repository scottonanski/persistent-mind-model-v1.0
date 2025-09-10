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
from pmm.runtime.embeddings import compute_embedding as _emb, cosine_similarity as _cos


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
        """Detect "Done:" style evidence and emit candidate then close with confirmation.

        NOTE: This legacy helper now follows the event-native flow:
        - Append an `evidence_candidate` event (if any match is detected)
        - Immediately attempt a confirmation close using the same deterministic rules
          so that test suites relying on prior behavior still observe closures.
          The close event will always appear AFTER the candidate event.

        Returns list of closed cids (0 or 1 element currently).
        """
        if not text:
            return []
        # Guard: require an explicit completion cue to avoid closing on plan statements
        _done_guard = _re.compile(r"\b(?:done|completed|finished)\b", _re.IGNORECASE)
        if not _done_guard.search(text or ""):
            return []

        # Build recent events slice and open commitments list
        events = self.eventlog.read_all()
        model = build_self_model(events)
        open_map: Dict[str, Dict] = model.get("commitments", {}).get("open", {})
        if not open_map:
            return []

        open_list = [
            {"cid": cid, "text": str((meta or {}).get("text") or "")}
            for cid, meta in open_map.items()
        ]

        # Run evidence finder over a small recent window including this text
        recent_window = 20
        # Use only the immediate reply as the recent window to ensure deterministic behavior
        tmp_events = [{"kind": "response", "content": text, "meta": {}}]
        cands = self.find_evidence(tmp_events, open_list, recent_window=recent_window)
        # Append top candidate (if any) and then close deterministically
        closed: List[str] = []
        if cands:
            # choose best by score then stable by cid
            cands_sorted = sorted(cands, key=lambda t: (-float(t[1]), str(t[0])))
            cid, score, snippet = cands_sorted[0]
            # Enforce deterministic threshold
            if float(score) < 0.70:
                return []
            # Idempotent candidate append: avoid duplicate immediate candidate
            already = False
            for ev in reversed(events):
                if ev.get("kind") != "evidence_candidate":
                    continue
                m = ev.get("meta") or {}
                if m.get("cid") == cid and m.get("snippet") == snippet:
                    already = True
                    break
            if not already:
                self.eventlog.append(
                    kind="evidence_candidate",
                    content="",
                    meta={"cid": cid, "score": float(score), "snippet": snippet},
                )
            # Immediately confirm and close using text-only policy
            ok = self.close_with_evidence(
                cid, evidence_type="done", description=text, artifact=None
            )
            if ok:
                closed.append(cid)
        return closed

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

    # --- Evidence finding (deterministic, rule-based) ---
    def find_evidence(
        self,
        events: List[Dict],
        open_commitments: List[Dict],
        recent_window: int = 20,
    ) -> List[tuple[str, float, str]]:
        """
        Returns a list of (cid, score, snippet) for candidate evidence found in the
        recent window. Deterministic scoring; no side effects.

        Scoring:
        - Exact/substring match of promise key phrase -> +0.6
        - Keyword map overlap (static dict) -> +0.2 per hit (capped so total <=1.0)
        - Completion verbs present -> +0.2
        Threshold handled by caller. Snippet is a <=160 char window around the match.
        """

        # Normalize helper
        def _norm(s: str) -> str:
            return " ".join((s or "").strip().lower().split())

        # Build recent text corpus from last `recent_window` assistant/user-like events
        # In this codebase, assistant replies are `response`; tests may inject plain events
        tail: List[Dict] = []
        for ev in reversed(events):
            if ev.get("kind") in {"response", "user", "reflection"}:
                tail.append(ev)
                if len(tail) >= recent_window:
                    break
        tail = list(reversed(tail))
        concat = "\n".join([str(e.get("content") or "") for e in tail])
        low = _norm(concat)

        # Extract last detail after a completion cue, if present
        done_re = _re.compile(
            r"\b(?:done|completed|finished)\s*:?\s*(.*)$", _re.IGNORECASE
        )
        detail_low = ""
        for ln in reversed(low.splitlines()):
            m = done_re.search(ln)
            if m:
                detail_low = _norm(m.group(1) or "")
                break
        # Compute embeddings once for detail (or low) if provider available
        emb_detail = _emb(detail_low or low)

        # Static completion verbs and keyword map
        completion_verbs = (
            "done",
            "completed",
            "finished",
            "shipped",
            "implemented",
            "merged",
            "wrote",
            "tested",
        )
        keyword_map = {
            "report": {"report", "write", "wrote", "draft", "pushed"},
            "code": {"code", "implement", "implemented", "commit", "merge"},
            "test": {"test", "tested", "ci", "green"},
            "docs": {"doc", "docs", "documentation", "wrote", "updated", "probe"},
            "summary": {"summary", "summarize", "prepared", "draft"},
        }
        stop = {"i", "will", "the", "a", "an", "to", "and", "of", "for", "today"}

        # Tiny lemmatizer for a few forms used in tests and common phrasing
        def _lemma_token(tok: str) -> str:
            m = {
                "wrote": "write",
                "written": "write",
                "writes": "write",
                "finish": "finish",
                "finished": "finish",
                "finishes": "finish",
                "finishing": "finish",
                "summarized": "summarize",
                "summaries": "summary",
                "docs": "doc",
                "documentation": "doc",
            }
            return m.get(tok, tok)

        import re as _re_local

        def _tokens(s: str) -> List[str]:
            # Replace non-alphanumeric with space, split, lower, lemmatize, drop stopwords
            s2 = _re_local.sub(r"[^a-z0-9]+", " ", (s or "").lower())
            toks = [t for t in s2.split() if t and t not in stop]
            return [_lemma_token(t) for t in toks]

        results: List[tuple[str, float, str]] = []
        for item in open_commitments:
            cid = str(item.get("cid"))
            text = _norm(str(item.get("text") or ""))
            if not cid or not text:
                continue
            score = 0.0
            snippet = ""
            # exact/substring between promise text and the detail or whole low
            hay = detail_low or low
            if text and text in hay or (detail_low and detail_low in text):
                score += 0.6
                # create snippet window
                idx = max(0, (concat.lower()).find((detail_low or text)))
                raw = concat
                # best-effort snippet from original concat around index
                snippet = raw[max(0, idx - 40) : idx + len(detail_low or text) + 40]
            # keyword overlaps
            for key, words in keyword_map.items():
                if key in text:
                    dl = detail_low or low
                    # check presence of base and a few lemmatized forms
                    hits = 0
                    for w in words:
                        w2 = _lemma_token(w)
                        if (" " + w + " ") in (" " + dl + " ") or (" " + w2 + " ") in (
                            " " + dl + " "
                        ):
                            hits += 1
                    if hits > 0:
                        score += min(0.2 * hits, 0.4)  # cap contribution
                        if not snippet:
                            snippet = key
            # token overlap between commitment and detail
            if detail_low:
                toks_text = _tokens(text)
                dl_toks = set(_tokens(detail_low))
                hits2 = sum(1 for t in toks_text if t in dl_toks)
                if hits2 > 0:
                    score += min(0.35 * hits2, 0.7)
                    if not snippet:
                        snippet = detail_low
            # completion verbs
            if any(v in low for v in completion_verbs):
                score += 0.2

            # Embedding similarity as alternate score (prefer max between heuristic and cosine)
            if emb_detail is not None:
                emb_text = _emb(text)
                if emb_text is not None:
                    sim = _cos(emb_detail, emb_text)
                    if sim > score:
                        score = float(sim)

            if score > 1.0:
                score = 1.0
            if score < 0:
                score = 0.0

            if score >= 0.0:
                # truncate snippet
                snippet = (snippet or text)[:160]
                results.append((cid, float(score), snippet))

        # Filter by threshold here? Caller will decide which to emit.
        # Sort for determinism (highest score first, then cid lexicographically)
        results.sort(key=lambda t: (-float(t[1]), str(t[0])))
        return results

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

    # --- TTL / Aging sweep ---
    def sweep_for_expired(self, events: List[Dict], ttl_ticks: int = 10) -> List[Dict]:
        """
        Return a list of expiration candidates as dicts {"cid": str, "reason": "timeout"}.
        Rules (deterministic):
        - Compute current tick as count of autonomy_tick events.
        - For each open commitment (open without close/expire), if age_in_ticks >= ttl_ticks and
          not snoozed beyond current tick, mark for expiration.
        - Age in ticks is (#autonomy_tick up to now) - (#autonomy_tick up to open_event).
        - Snooze: if a commitment_snooze exists for cid with until_tick > current_tick, skip.
        """
        if not events:
            return []
        # Current tick
        curr_tick = sum(1 for ev in events if ev.get("kind") == "autonomy_tick")
        # Track opens and closes/expires by cid
        open_event_by_cid: Dict[str, Dict] = {}
        closed_or_expired: set[str] = set()
        for ev in events:
            k = ev.get("kind")
            if k == "commitment_open":
                cid = (ev.get("meta") or {}).get("cid")
                if cid:
                    open_event_by_cid[str(cid)] = ev
            elif k in ("commitment_close", "commitment_expire"):
                cid = (ev.get("meta") or {}).get("cid")
                if cid:
                    closed_or_expired.add(str(cid))
        # Build snooze map (latest wins)
        snooze_until: Dict[str, int] = {}
        for ev in events:
            if ev.get("kind") == "commitment_snooze":
                m = ev.get("meta") or {}
                cid = str(m.get("cid") or "")
                try:
                    until_t = int(m.get("until_tick") or 0)
                except Exception:
                    until_t = 0
                if cid:
                    snooze_until[cid] = max(snooze_until.get(cid, 0), until_t)

        # Helper: compute tick at an event id
        def _tick_at_event_id(eid: int) -> int:
            t = 0
            for ev in events:
                if ev.get("kind") == "autonomy_tick":
                    t += 1
                if int(ev.get("id") or 0) >= eid:
                    break
            return t

        out: List[Dict] = []
        for cid, ev in open_event_by_cid.items():
            if cid in closed_or_expired:
                continue
            open_id = int(ev.get("id") or 0)
            open_tick = _tick_at_event_id(open_id)
            age = max(0, curr_tick - open_tick)
            # Snooze check: skip if snooze_until is not yet passed (inclusive)
            snooze_until_val = snooze_until.get(cid, None)
            if snooze_until_val is not None:
                if curr_tick <= snooze_until_val:
                    continue
            if age >= int(ttl_ticks):
                out.append({"cid": cid, "reason": "timeout"})
        return out

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
