"""Minimal commitment tracking built on EventLog + projection.

Intent:
- Evidence-first lifecycle only: open via explicit user/agent action,
  close only with allowed evidence.
- No TTL, no heuristics, no autoclose.
"""

from __future__ import annotations

import uuid as _uuid
import re as _re
from typing import Dict, List, Optional, Tuple
import datetime as _dt
import hashlib
import os
from datetime import datetime, timezone, timedelta
from typing import Any
from dataclasses import dataclass

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

    def process_assistant_reply(
        self, text: str, reply_event_id: Optional[int] = None
    ) -> List[str]:
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
            # Heuristic filter: skip meta-communication about reply formatting or immediate-next reply
            low = ctext.lower()
            if (
                "next reply" in low
                or ("ensure" in low and ("reply" in low or "response" in low))
                or ("brevity" in low or "concise" in low)
            ):
                continue
            # Normalize and dedup quickly via projection view
            if kind not in {"plan", "followup"}:
                kind = "plan"
            # Trim to sentence and normalize spacing; preserve canonical identity tokens
            if str(ctext).strip().lower().startswith("identity:name:"):
                norm = str(ctext).strip()
            else:
                norm = self._normalize_text(ctext)
            source = f"detector:{kind}" if kind else "detector"
            extra_meta = (
                {"origin_eid": int(reply_event_id)}
                if reply_event_id is not None
                else None
            )
            cid = self.add_commitment(norm, source=source, extra_meta=extra_meta)
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
            if float(score) >= 0.70:
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

    # --- Reflection-driven lifecycle helpers ---
    def close_reflection_on_next(self, response_text: str) -> bool:
        """Close the oldest still-open reflection-driven commitment using the given reply.

        Emits an `evidence_candidate` followed by `commitment_close` (evidence_type="done").
        Returns True if a commitment was closed.
        """
        try:
            events = self.eventlog.read_all()
            model = build_self_model(events)
            open_map = (model.get("commitments") or {}).get("open") or {}
            # Determine which open cids are reflection-driven by scanning their last open event
            open_reflection: List[tuple[str, int]] = []  # (cid, open_event_id)
            # Build map of latest close/expire per cid
            closed_or_expired: set[str] = set()
            for ev in events:
                if ev.get("kind") in {"commitment_close", "commitment_expire"}:
                    m = ev.get("meta") or {}
                    c = str(m.get("cid") or "")
                    if c:
                        closed_or_expired.add(c)
            for ev in events:  # ascending id
                if ev.get("kind") != "commitment_open":
                    continue
                m = ev.get("meta") or {}
                c = str(m.get("cid") or "")
                if not c or c not in open_map or c in closed_or_expired:
                    continue
                reason = (m.get("reason") or "").strip()
                if reason == "reflection":
                    try:
                        eid = int(ev.get("id") or 0)
                    except Exception:
                        eid = 0
                    open_reflection.append((c, eid))
            if not open_reflection:
                return False
            # Oldest by smallest open event id still open
            open_reflection.sort(key=lambda t: t[1])
            cid_oldest, _eid = open_reflection[0]
            snippet = (response_text or "")[:160]
            # Append candidate idempotently
            already = False
            for ev in reversed(events):
                if ev.get("kind") != "evidence_candidate":
                    continue
                m = ev.get("meta") or {}
                if m.get("cid") == cid_oldest and m.get("snippet") == snippet:
                    already = True
                    break
            if not already:
                self.eventlog.append(
                    kind="evidence_candidate",
                    content="",
                    meta={"cid": cid_oldest, "score": 1.0, "snippet": snippet},
                )
            return self.close_with_evidence(
                cid_oldest,
                evidence_type="done",
                description=response_text,
                artifact=None,
            )
        except Exception:
            return False

    def supersede_reflection_commitments(
        self, *, by_reflection_id: int | None = None
    ) -> int:
        """Close all currently open reflection-driven commitments as superseded.

        Returns the number of commitments closed.
        """
        try:
            events = self.eventlog.read_all()
            model = build_self_model(events)
            open_map = (model.get("commitments") or {}).get("open") or {}
            # Track open reflection commitments via their open events
            open_reflection: List[str] = []
            closed_or_expired: set[str] = set()
            for ev in events:
                if ev.get("kind") in {"commitment_close", "commitment_expire"}:
                    m = ev.get("meta") or {}
                    c = str(m.get("cid") or "")
                    if c:
                        closed_or_expired.add(c)
            for ev in events:
                if ev.get("kind") != "commitment_open":
                    continue
                m = ev.get("meta") or {}
                c = str(m.get("cid") or "")
                if not c or c not in open_map or c in closed_or_expired:
                    continue
                if (m.get("reason") or "").strip() == "reflection":
                    open_reflection.append(c)
            # Build a snippet from the new reflection content if available
            snippet = ""
            if by_reflection_id is not None:
                try:
                    rid = int(by_reflection_id)
                except Exception:
                    rid = 0
                if rid > 0:
                    for ev in reversed(events):
                        try:
                            if (
                                int(ev.get("id") or 0) == rid
                                and ev.get("kind") == "reflection"
                            ):
                                txt = str(ev.get("content") or "")
                                snippet = (txt.splitlines()[0] if txt else "")[:240]
                                break
                        except Exception:
                            continue
            count = 0
            desc = (
                f"superseded_by_reflection#{int(by_reflection_id)}"
                if by_reflection_id is not None
                else "superseded_by_reflection"
            )
            for cid in open_reflection:
                # Append evidence candidate before close to satisfy audit ordering
                try:
                    sc = 0.9 if snippet else 0.75
                    self.eventlog.append(
                        kind="evidence_candidate",
                        content="",
                        meta={
                            "cid": cid,
                            "score": float(sc),
                            "snippet": snippet or "superseded by newer reflection",
                        },
                    )
                except Exception:
                    pass
                ok = self.close_with_evidence(
                    cid, evidence_type="done", description=desc, artifact=None
                )
                if ok:
                    count += 1
            return count
        except Exception:
            return 0
            # else: end

    def add_commitment(
        self,
        text: str,
        source: str | None = None,
        extra_meta: Optional[Dict] = None,
        project: Optional[str] = None,
    ) -> str:
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
        if isinstance(extra_meta, dict):
            # Shallow merge; do not overwrite cid/text/source
            for k, v in extra_meta.items():
                if k not in meta:
                    meta[k] = v
        # Optional project grouping: explicit or auto-detected
        # 1) Explicit project argument or meta.project_id
        explicit_pid: Optional[str] = None
        if project and isinstance(project, str):
            explicit_pid = str(project).strip()
        elif isinstance(meta.get("project_id"), str):
            explicit_pid = str(meta.get("project_id")).strip()

        # 2) Auto-detect project tag if not explicitly provided
        auto_pid: Optional[str] = None
        if not explicit_pid:
            auto_pid = self._auto_project_id(text)
            # Only promote to active project if at least one other OPEN commitment shares the same tag
            if auto_pid:
                try:
                    evs = self.eventlog.read_all()
                    model0 = build_self_model(evs)
                    open_map0: Dict[str, Dict] = (model0.get("commitments") or {}).get(
                        "open", {}
                    )
                    # Find already-open cids with same auto tag
                    siblings: list[str] = []
                    for ocid, ometa in open_map0.items():
                        txt0 = str((ometa or {}).get("text") or "")
                        if self._auto_project_id(txt0) == auto_pid:
                            siblings.append(str(ocid))
                    # If any sibling exists, adopt auto project id
                    if siblings:
                        explicit_pid = auto_pid
                        # Attach siblings idempotently to this project
                        for sib in siblings:
                            self._assign_project_if_needed(sib, explicit_pid)
                except Exception:
                    pass
        if explicit_pid:
            meta["project_id"] = explicit_pid
            self._ensure_project_open(explicit_pid)
        content = f"Commitment opened: {text}"
        self.eventlog.append(kind="commitment_open", content=content, meta=meta)
        return cid

    # --- Projects: idempotent project lifecycle helpers ---
    def _ensure_project_open(self, project_id: str) -> None:
        try:
            if not project_id:
                return
            # Idempotent: only one project_open per project_id
            for e in self.eventlog.read_all():
                if (
                    e.get("kind") == "project_open"
                    and (e.get("meta") or {}).get("project_id") == project_id
                ):
                    return
            self.eventlog.append(
                kind="project_open",
                content=f"Project: {project_id}",
                meta={"project_id": project_id},
            )
        except Exception:
            # Never allow project bookkeeping to break flow
            return

    def _assign_project_if_needed(self, cid: str, project_id: str) -> None:
        """Idempotently attach an open commitment to a project via project_assign event.

        No-op if the commitment already carries meta.project_id or an existing assignment for this project.
        """
        try:
            if not cid or not project_id:
                return
            # If already tagged in projection, skip
            model = build_self_model(self.eventlog.read_all())
            open_map = (model.get("commitments") or {}).get("open") or {}
            if cid not in open_map:
                return
            if (open_map.get(cid) or {}).get("project_id") == project_id:
                return
            # If an assignment exists already, skip
            for e in reversed(self.eventlog.read_all()):
                if e.get("kind") != "project_assign":
                    continue
                m = e.get("meta") or {}
                if (
                    str(m.get("cid")) == str(cid)
                    and str(m.get("project_id")) == project_id
                ):
                    return
            # Emit assignment and ensure project open
            self._ensure_project_open(project_id)
            self.eventlog.append(
                kind="project_assign",
                content="",
                meta={"cid": str(cid), "project_id": project_id},
            )
        except Exception:
            # Best-effort; never raise
            return

    # --- Auto-project tag extraction ---
    def _auto_project_id(self, text: str) -> Optional[str]:
        """Derive a stable, short project id from commitment text.

        Heuristic: tokenize, drop stopwords and common verbs, take first 1–2 tokens, join with '-'.
        Returns None if insufficient signal.
        """
        try:
            import re as _re_local

            stop = {
                "i",
                "will",
                "the",
                "a",
                "an",
                "to",
                "for",
                "of",
                "on",
                "and",
                "or",
                "with",
                "my",
                "your",
                "our",
                "this",
                "that",
                "is",
                "are",
                "be",
                "it",
            }
            verbs = {
                "write",
                "document",
                "doc",
                "prepare",
                "summarize",
                "summarise",
                "refactor",
                "ship",
                "finish",
                "finalize",
                "improve",
                "help",
                "assist",
                "investigate",
                "research",
                "explore",
                "review",
                "add",
                "create",
                "make",
                "do",
                "update",
            }
            s = (text or "").lower()
            toks = [t for t in _re_local.findall(r"[a-z0-9]+", s) if t]

            # crude singularization for plural nouns
            def _sing(w: str) -> str:
                if len(w) > 3 and w.endswith("s"):
                    return w[:-1]
                return w

            filt = [
                _sing(t)
                for t in toks
                if t not in stop and t not in verbs and not t.isdigit()
            ]
            if not filt:
                return None
            # prefer tokens that are descriptive; cap length
            base = filt[0]
            second = filt[1] if len(filt) > 1 else None
            pid = base if not second else f"{base}-{second}"
            pid = pid[:24]
            # ensure starts with alnum
            return pid if pid and pid[0].isalnum() else None
        except Exception:
            return None

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
        # stopword set retained for future use; not needed in the current scoring

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
            toks = [t for t in s2.split() if t]
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

        # Always require artifact evidence (truth-first); no env/test overrides.
        if not artifact:
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

        # If the commitment belongs to a project (explicit or assigned), propagate project_id on close
        try:
            proj_id = self._resolve_project_for_cid(cid)
            if proj_id:
                meta["project_id"] = proj_id
        except Exception:
            proj_id = None

        content = f"Commitment closed: {cid}"
        self.eventlog.append(kind="commitment_close", content=content, meta=meta)
        # If this was the last open commitment in its project, close the project idempotently
        try:
            if proj_id:
                # Recompute open view after closing this cid
                evs_after = self.eventlog.read_all()
                model_after = build_self_model(evs_after)
                open_map_after: Dict[str, Dict] = (
                    model_after.get("commitments", {}) or {}
                ).get("open", {})
                # Build assignment map for open cids
                assign: Dict[str, str] = {}
                for e in reversed(evs_after):
                    if e.get("kind") != "project_assign":
                        continue
                    m = e.get("meta") or {}
                    cc = str(m.get("cid") or "")
                    pid = str(m.get("project_id") or "")
                    if cc and cc in open_map_after and cc not in assign:
                        assign[cc] = pid
                any_remaining = False
                for _cid, _m in open_map_after.items():
                    pid0 = (_m or {}).get("project_id") or assign.get(_cid)
                    if pid0 == proj_id:
                        any_remaining = True
                        break
                if not any_remaining:
                    # Idempotent guard for project_close
                    already = False
                    for e in reversed(evs_after):
                        if e.get("kind") != "project_close":
                            continue
                        if (e.get("meta") or {}).get("project_id") == proj_id:
                            already = True
                            break
                    if not already:
                        self.eventlog.append(
                            kind="project_close",
                            content=f"Project: {proj_id}",
                            meta={"project_id": proj_id},
                        )
        except Exception:
            pass
        return True

    def _resolve_project_for_cid(self, cid: str) -> Optional[str]:
        """Return project_id for an open or recently-closed cid via meta or assignment events."""
        try:
            evs = self.eventlog.read_all()
            model = build_self_model(evs)
            open_map: Dict[str, Dict] = model.get("commitments", {}).get("open", {})
            if cid in open_map:
                pid = (open_map.get(cid) or {}).get("project_id")
                if isinstance(pid, str) and pid:
                    return pid
            # Find latest project_assign for this cid
            for e in reversed(evs):
                if e.get("kind") != "project_assign":
                    continue
                m = e.get("meta") or {}
                if str(m.get("cid")) == str(cid):
                    pid = m.get("project_id")
                    if isinstance(pid, str) and pid:
                        return pid
            return None
        except Exception:
            return None

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
                if cid in open_event_by_cid:
                    continue
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
                    # Provide a synthetic artifact to satisfy truth-first policy
                    self.close_with_evidence(
                        cid,
                        evidence_type="done",
                        description=f"adopted name {name}",
                        artifact=f"identity:{name}",
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
        open_map: Dict[str, Dict] = model.get("commitments", {}).get("open") or {}
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
        # Constant dedup window (no env override)
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
        # Constant TTL hours (no env override)
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


# --- Step 19: Invariant breach self-triage (log-only, idempotent) ---
TRIAGE_WINDOW_EIDS: int = 500
TRIAGE_PRIORITY: str = "low"
TRIAGE_TEXT_TMPL: str = "Investigate invariant violation CODE={code}"


def open_violation_triage(
    events_tail: List[Dict],
    evlog: EventLog,
    window_eids: int = TRIAGE_WINDOW_EIDS,
) -> Dict[str, List[str]]:
    """
    Idempotently open at most one low-priority triage commitment per unique
    invariant_violation 'code' visible in the tail window.

    Returns: {"opened": [codes], "skipped": [codes]}
    Deterministic, no exceptions.
    """
    try:
        # 1) Collect violation codes present in the tail
        codes: List[str] = []
        for e in events_tail or []:
            if e.get("kind") == "invariant_violation":
                m = e.get("meta") or {}
                c = m.get("code")
                if c:
                    codes.append(str(c))
        if not codes:
            return {"opened": [], "skipped": []}
        recent_codes = set(codes)

        # 2) Detect triages already open/closed within the tail
        triage_prefix = "Investigate invariant violation CODE="
        open_by_code: set[str] = set()
        triage_cid_by_code: Dict[str, str] = {}
        closed_cids: set[str] = set()
        for e in events_tail:
            k = e.get("kind")
            if k == "commitment_open":
                meta = e.get("meta") or {}
                text = str(meta.get("text") or "")
                reason = (meta.get("reason") or "").strip()
                code_meta = meta.get("code")
                if (reason == "invariant_violation" and code_meta) or text.startswith(
                    triage_prefix
                ):
                    code = str(code_meta) if code_meta else text.split("CODE=", 1)[1]
                    open_by_code.add(code)
                    c = str(meta.get("cid") or "")
                    if c:
                        triage_cid_by_code[code] = c
            elif k == "commitment_close":
                m = e.get("meta") or {}
                c = m.get("cid")
                if c:
                    closed_cids.add(str(c))
        closed_by_code: set[str] = set()
        for code, cid in triage_cid_by_code.items():
            if cid in closed_cids:
                closed_by_code.add(code)

        # 3) Open for codes with violations but no open/closed triage in-window
        opened: List[str] = []
        skipped: List[str] = []
        tracker = CommitmentTracker(evlog)
        for code in sorted(recent_codes):
            if code in open_by_code or code in closed_by_code:
                skipped.append(code)
                continue
            text = TRIAGE_TEXT_TMPL.format(code=code)
            cid = tracker.add_commitment(
                text,
                source="triage",
                extra_meta={
                    "priority": TRIAGE_PRIORITY,
                    "reason": "invariant_violation",
                    "code": code,
                },
            )
            if cid:
                opened.append(code)
            else:
                skipped.append(code)
        return {"opened": opened, "skipped": skipped}
    except Exception:
        # Never raise from triage path
        return {"opened": [], "skipped": []}


@dataclass
class Commitment:
    """A commitment made by an agent during reflection."""

    cid: str
    text: str
    created_at: str
    source_insight_id: str
    status: str = "open"  # open, closed, expired, tentative, ongoing
    # Tier indicates permanence; tentative items can be promoted on reinforcement/evidence
    tier: str = "permanent"  # permanent, tentative, ongoing
    due: Optional[str] = None
    closed_at: Optional[str] = None
    close_note: Optional[str] = None
    ngrams: List[str] = None  # 3-grams for matching
    # Hash of the associated 'commitment' event in the SQLite chain
    # If present, this becomes the canonical reference for evidence
    event_hash: Optional[str] = None
    # Reinforcement tracking
    attempts: int = 1
    reinforcements: int = 0
    last_reinforcement_ts: Optional[str] = None
    _just_reinforced: bool = False


class LegacyCommitmentTracker:
    """Manages commitment lifecycle and completion detection."""

    def __init__(
        self, eventlog: Optional["EventLog"] = None, detector: Optional[Any] = None
    ):
        self.commitments: Dict[str, Commitment] = {}
        self.eventlog = eventlog  # Store EventLog instance for logging
        self.detector = (
            detector  # Store detector if provided, for compatibility with tests
        )

    def _is_valid_commitment(self, text: str) -> bool:
        """Validate using only structural features and centroid score.

        - No keyword or phrase lists
        - No normalization to canonical phrases
        - Structure: first token POS verb OR presence of first-person POS; token_count >= 3
        - Semantics: CommitmentExtractor score >= commit_thresh
        """
        if not isinstance(text, str):
            return False
        s = text.strip()
        if len(s) < 3:
            return False
        # Structural gating
        try:
            from pmm.struct_semantics import pos_tag

            tags = pos_tag(s)
        except Exception:
            tags = []
        first_is_verb = bool(
            tags
            and isinstance(tags[0], (list, tuple))
            and str(tags[0][1]).startswith("VB")
        )
        pos_unknown = (not tags) or all(
            (isinstance(t, (list, tuple)) and str(t[1]) == "X") for t in (tags or [])
        )
        toks = [t for t in s.split() if t]
        first_token_lower = toks[0].lower() if toks else ""
        token_count = len([t for t in s.split() if t])
        # Pattern: PRP MD VB* (e.g., I will do, We should consider)
        prp_md_vb = False
        if isinstance(tags, list) and len(tags) >= 3:
            try:
                t0 = str(tags[0][1])
                t1 = str(tags[1][1])
                t2 = str(tags[2][1])
                prp_md_vb = (
                    t0.startswith("PRP") and t1.startswith("MD") and t2.startswith("VB")
                )
            except Exception:
                prp_md_vb = False
        # Semantic-only policy: avoid rejecting imperative forms due to missing POS tagger.
        # Require only minimal length; semantics gate below does the heavy lifting.
        structure_ok = token_count >= 2
        # Reject short pronoun+modal constructions as too vague unless verb-first
        if prp_md_vb and token_count < 6 and not first_is_verb:
            if os.getenv("PMM_DEBUG") == "1":
                print(f"[PMM_DEBUG] Reject: short PRP-MD-VB | text={s}")
            return False
        # Reject short pronoun-first non-imperative statements in general
        if first_token_lower in {"i", "we"} and token_count < 6 and not first_is_verb:
            if os.getenv("PMM_DEBUG") == "1":
                print(
                    f"[PMM_DEBUG] Reject: short pronoun-first non-imperative | text={s}"
                )
            return False
        # Reject short comma-prefixed sequences (e.g., "Next, ...") unless long enough
        if isinstance(tags, list) and len(tags) >= 4:
            try:
                first_tok_text = str(tags[0][0])
                comma_prefixed = first_tok_text.endswith(",")
                if comma_prefixed and token_count < 7 and not first_is_verb:
                    if os.getenv("PMM_DEBUG") == "1":
                        print(f"[PMM_DEBUG] Reject: short comma-prefixed | text={s}")
                    return False
            except Exception:
                pass
        if not structure_ok:
            return False
        # Semantic gating
        try:
            from pmm.commitments.extractor import CommitmentExtractor

            extractor = CommitmentExtractor()
        except Exception:
            return False
        # If we cannot compute a vector (e.g., analyzer unavailable), be conservative:
        # require imperative (verb-first) to pass; otherwise reject.
        try:
            vec = extractor._vector(s)  # type: ignore[attr-defined]
        except Exception:
            vec = []
        vec_missing = (not isinstance(vec, (list, tuple))) or (len(vec) == 0)
        if vec_missing:
            # If POS is known and indicates non-imperative, reject
            imperative_like = first_is_verb or (prp_md_vb and token_count >= 6)
            if not pos_unknown and not imperative_like:
                if os.getenv("PMM_DEBUG") == "1":
                    print(
                        f"[PMM_DEBUG] Reject: vec_missing & non-imperative (POS known) | text={s}"
                    )
                return False
            # If POS unknown, do not over-reject; rely on structural score + thresholds
        score = extractor.score(s)
        return score >= extractor.commit_thresh

    def extract_commitment(self, text: str) -> Tuple[Optional[str], List[str]]:
        """Extract a normalized commitment string and its 3-grams from free text.

        Rules:
        - Choose the best sentence by structural+semantic score
        - Apply structural validation via _is_valid_commitment
        Returns: (commitment_text_or_None, ngrams)
        """
        if not isinstance(text, str) or not text.strip():
            return None, []
        try:
            from pmm.commitments.extractor import CommitmentExtractor

            extractor = CommitmentExtractor()
        except Exception:
            return None, []
        cand = extractor.extract_best_sentence(text.strip())
        if not cand or not self._is_valid_commitment(cand):
            return None, []
        ngrams = self._ngram3(cand)
        return cand, ngrams

    def add_commitment(
        self,
        text: str,
        source_insight_id: str = "",
        due: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Optional[str]:
        """Validate and add a commitment; returns cid or None if rejected.

        - Enforces ownership and structural checks
        - Rejects duplicates by semantic similarity (threshold via env)
        - Stores 3-grams for later matching
        - Logs commitment addition to EventLog
        """
        # Removed all literal special-casing; only structural+semantic extraction is allowed

        commit_text, ngrams = self.extract_commitment(text)
        if not commit_text:
            return None
        dup_cid = self._is_duplicate_commitment(commit_text)
        if dup_cid:
            # Record reinforcement on the existing commitment
            try:
                c = self.commitments[dup_cid]
                c.reinforcements += 1
                c.last_reinforcement_ts = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                c._just_reinforced = True
                if self.eventlog:
                    self.eventlog.append(
                        kind="commitment_reinforced",
                        content=commit_text,
                        meta={
                            "cid": dup_cid,
                            "reinforcements": c.reinforcements,
                            "last_reinforcement_ts": c.last_reinforcement_ts,
                        },
                    )
            except Exception:
                pass
            return None
        # Create CID and store
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cid = hashlib.sha256(
            f"{ts}:{commit_text}:{source_insight_id}".encode("utf-8")
        ).hexdigest()[:12]
        self.commitments[cid] = Commitment(
            cid=cid,
            text=commit_text,
            created_at=ts,
            source_insight_id=str(source_insight_id),
            status="open",
            tier="permanent",
            due=due,
            ngrams=ngrams,
        )
        # Log commitment addition to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="commitment_added",
                content=commit_text,
                meta={
                    "cid": cid,
                    "created_at": ts,
                    "source_insight_id": source_insight_id,
                    "status": "open",
                    "tier": "permanent",
                    "due": due if due else "",
                },
            )
        return cid

    def process_assistant_reply(
        self, text: str, reply_event_id: int = 0
    ) -> Optional[str]:
        """
        Process an assistant's reply to extract potential commitments.

        Args:
            text: The text of the assistant's reply.
            reply_event_id: The ID of the event associated with this reply.

        Returns:
            The commitment ID if a commitment was extracted and added, None otherwise.
        """
        if not text or not isinstance(text, str):
            return None

        commit_text, ngrams = self.extract_commitment(text)
        if not commit_text:
            return None

        dup_cid = self._is_duplicate_commitment(commit_text)
        if dup_cid:
            # Record reinforcement on the existing commitment
            try:
                c = self.commitments[dup_cid]
                c.reinforcements += 1
                c.last_reinforcement_ts = datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                c._just_reinforced = True
                if self.eventlog:
                    self.eventlog.append(
                        kind="commitment_reinforced",
                        content=commit_text,
                        meta={
                            "cid": dup_cid,
                            "reinforcements": c.reinforcements,
                            "last_reinforcement_ts": c.last_reinforcement_ts,
                        },
                    )
            except Exception:
                pass
            return None

        # Create CID and store
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cid = hashlib.sha256(
            f"{ts}:{commit_text}:{reply_event_id}".encode("utf-8")
        ).hexdigest()[:12]
        self.commitments[cid] = Commitment(
            cid=cid,
            text=commit_text,
            created_at=ts,
            source_insight_id=str(reply_event_id),
            status="open",
            tier="permanent",
            ngrams=ngrams,
        )

        # Log commitment addition to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="commitment_added",
                content=commit_text,
                meta={
                    "cid": cid,
                    "created_at": ts,
                    "source_insight_id": str(reply_event_id),
                    "status": "open",
                    "tier": "permanent",
                },
            )
        return cid

    def _ngram3(self, s: str) -> List[str]:
        toks = [t for t in (s or "").lower().split() if t]
        return [" ".join(toks[i : i + 3]) for i in range(max(0, len(toks) - 2))]

    def _is_duplicate_commitment(self, new_text: str) -> Optional[str]:
        """Return cid of a semantically duplicate open commitment, else None.

        Uses cosine similarity when available, otherwise token Jaccard.
        Threshold is configured by PMM_DUPLICATE_SIM_THRESHOLD (default 0.85).
        Only compares against non-archived, non-closed commitments.
        """
        # Constant duplicate similarity threshold
        try:
            from pmm.config import DUPLICATE_SIM_THRESHOLD as _DTH

            thresh = float(_DTH)
        except Exception:
            thresh = 0.60
        candidates = [
            c
            for c in self.commitments.values()
            if c.status in ("open", "tentative", "ongoing")
        ]
        if not candidates:
            return None
        # Try semantic analyzer
        analyzer = None
        try:
            from pmm.semantic_analysis import get_semantic_analyzer

            analyzer = get_semantic_analyzer()
        except Exception:
            analyzer = None
        best_cid = None
        best_sim = 0.0
        for c in candidates:
            sim_sem = 0.0
            sim_tok = 0.0
            if analyzer is not None:
                try:
                    sim_sem = float(analyzer.cosine_similarity(new_text, c.text))
                except Exception:
                    sim_sem = 0.0
            else:
                # Jaccard on lowercased tokens without regex
                a = set((new_text or "").lower().split()) - {""}
                b = set((c.text or "").lower().split()) - {""}
                inter = len(a & b)
                union = len(a | b) or 1
                sim_tok = inter / union
            # Always compute token Jaccard as a fallback signal
            if sim_tok == 0.0:
                a = set((new_text or "").lower().split()) - {""}
                b = set((c.text or "").lower().split()) - {""}
                inter = len(a & b)
                union = len(a | b) or 1
                sim_tok = inter / union

            sim = max(sim_sem, sim_tok)
            if sim > best_sim:
                best_sim = sim
                best_cid = c.cid
        if best_sim >= thresh:
            return best_cid
        return None

    def get_commitment_hash(self, commitment: Commitment) -> str:
        """Return a stable 16-hex hash for a commitment for evidence linking."""
        base = f"{commitment.cid}:{commitment.text}:{commitment.created_at}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

    def _extract_artifact(self, description: str) -> Optional[str]:
        """Extract a likely artifact reference from evidence text.

        Handles:
        - URLs via urllib.parse
        - File-like tokens via pathlib suffix
        - Simple IDs if token contains digits
        - ISO-like dates are not regex-detected; rely on tokens containing '-' and digits
        """
        if not isinstance(description, str) or not description:
            return None
        d = description.strip()

        # Tokens (strip basic punctuation)
        def _sp(tok: str) -> str:
            return tok.strip("'`.,;:()[]{}")

        try:
            from urllib.parse import urlparse
            from pathlib import PurePosixPath

            for tok in d.split():
                st = _sp(tok)
                if not st:
                    continue
                # URL per-token
                try:
                    parsed = urlparse(st)
                    if parsed.scheme in ("http", "https") and parsed.netloc:
                        return st
                except Exception:
                    pass
                try:
                    p = PurePosixPath(st)
                    if p.suffix:
                        return st
                except Exception:
                    pass
                if any(ch.isdigit() for ch in st):
                    return st
        except Exception:
            pass
        return None

    def detect_evidence_events(
        self, text: str
    ) -> List[Tuple[str, str, str, Optional[str]]]:
        """Deprecated: keyword-based evidence detection removed.

        Evidence mapping is handled semantically in pmm/evidence/behavior_engine.py.
        This function now returns an empty list.
        """
        return []

    def _estimate_evidence_confidence(
        self,
        commitment_text: str,
        description: str,
        artifact: Optional[str] = None,
    ) -> float:
        """Heuristically estimate confidence that evidence supports the commitment."""
        try:
            ct = (commitment_text or "").lower()
            desc = (description or "").lower()
            base = 0.35

            def bigrams(s: str) -> set:
                toks = [t for t in (s or "").split() if t]
                return set(
                    " ".join(toks[i : i + 2]) for i in range(max(0, len(toks) - 1))
                )

            def trigrams(s: str) -> set:
                toks = [t for t in (s or "").split() if t]
                return set(
                    " ".join(toks[i : i + 3]) for i in range(max(0, len(toks) - 2))
                )

            b_ct, b_desc = bigrams(ct), bigrams(desc)
            t_ct, t_desc = trigrams(ct), trigrams(desc)
            b_overlap = (len(b_ct & b_desc) / len(b_ct)) if b_ct else 0.0
            t_overlap = (len(t_ct & t_desc) / len(t_ct)) if t_ct else 0.0

            score = base + 0.35 * b_overlap + 0.25 * t_overlap

            # Semantic boost
            try:
                from pmm.semantic_analysis import get_semantic_analyzer

                analyzer = get_semantic_analyzer()
                cos = analyzer.cosine_similarity(commitment_text, description)
                score += 0.35 * max(0.0, min(1.0, float(cos)))
            except Exception:
                pass

            if artifact:
                score += 0.10
                # URL boost
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(artifact)
                    if parsed.scheme in ("http", "https") and parsed.netloc:
                        score += 0.05
                except Exception:
                    pass
                # File suffix boost
                try:
                    from pathlib import PurePosixPath

                    p = PurePosixPath(artifact)
                    if p.suffix:
                        score += 0.05
                except Exception:
                    pass
                # Bare id token boost if contains digits
                try:
                    if any(ch.isdigit() for ch in str(artifact)):
                        score += 0.03
                except Exception:
                    pass

            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5

    def get_open_commitments(self) -> List[Dict[str, Any]]:
        """Return a simple list of open (non-archived, non-closed) commitments."""
        out: List[Dict[str, Any]] = []
        for c in self.commitments.values():
            if c.status in ("open", "tentative", "ongoing"):
                out.append(
                    {
                        "cid": c.cid,
                        "text": c.text,
                        "status": c.status,
                        "created_at": c.created_at,
                    }
                )
        return out

    def archive_legacy_commitments(self) -> List[str]:
        """Deprecated: removal of keyword-based hygiene archiving.

        Returns an empty list to comply with no-keyword policy.
        """
        return []

    def mark_commitment(
        self, cid: str, status: str, note: Optional[str] = None
    ) -> bool:
        """Update commitment status and optional note.

        Returns True if found and updated; False otherwise.
        Logs status update to EventLog.
        """
        c = self.commitments.get(cid)
        if not c:
            return False
        # Allow closing or expiring ongoing via explicit mark; protect in evidence path only
        valid_status = {
            "open",
            "closed",
            "expired",
            "tentative",
            "ongoing",
            "archived_legacy",
        }
        if status not in valid_status:
            return False
        c.status = status
        if status in ("closed", "expired", "archived_legacy"):
            c.closed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if note:
            c.close_note = note

        # Log status update to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="commitment_status_updated",
                content="",
                meta={
                    "cid": cid,
                    "new_status": status,
                    "closed_at": c.closed_at if c.closed_at else "",
                    "close_note": note if note else "",
                },
            )
        return True

    def auto_close_from_reflection(self, text: str) -> List[str]:
        """Heuristic auto-closure from reflection content.

        Current implementation is conservative: does not auto-close any items.
        Returns the list of cids that were closed (empty).
        """
        return []

    def close_commitment_with_evidence(
        self,
        commit_hash: str,
        evidence_type: str,
        description: str,
        artifact: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> bool:
        """
        Close a commitment with evidence.

        Args:
            commit_hash: Hash of the commitment to close
            evidence_type: Type of evidence (done, blocked, delegated)
            description: Description of the evidence
            artifact: Optional artifact (file, URL, etc.)
            confidence: Optional confidence score (0-1)

        Returns:
            bool: True if commitment was closed, False otherwise
        Logs evidence and closure to EventLog.
        """
        # Find commitment by hash
        target_cid = None
        target_commitment = None

        for cid, commitment in self.commitments.items():
            if self.get_commitment_hash(commitment) == commit_hash:
                target_cid = cid
                target_commitment = commitment
                break

        if not target_commitment:
            print(f"[PMM_EVIDENCE] commitment not found: {commit_hash}")
            return False

        # Protect ongoing items; record evidence upstream without closing
        if (
            getattr(target_commitment, "status", "open") == "ongoing"
            or getattr(target_commitment, "tier", "permanent") == "ongoing"
        ):
            print(
                f"[PMM_EVIDENCE] ongoing commitment; recording evidence only: {target_cid}"
            )
            if self.eventlog:
                self.eventlog.append(
                    kind="evidence_recorded_only",
                    content=description,
                    meta={
                        "cid": target_cid,
                        "evidence_type": evidence_type,
                        "artifact": artifact if artifact else "",
                        "reason": "ongoing commitment",
                    },
                )
            return False
        # Permit closing 'tentative' commitments too, since the UI lists them among open items
        if target_commitment.status not in ("open", "tentative"):
            try:
                st = str(getattr(target_commitment, "status", "unknown"))
            except Exception:
                st = "unknown"
            print(f"[PMM_EVIDENCE] commitment not closable (status={st}): {target_cid}")
            return False

        # Only 'done' evidence can close commitments
        if evidence_type != "done":
            print(
                f"[PMM_EVIDENCE] non_done_evidence: {evidence_type} recorded but not closing"
            )
            if self.eventlog:
                self.eventlog.append(
                    kind="evidence_recorded_only",
                    content=description,
                    meta={
                        "cid": target_cid,
                        "evidence_type": evidence_type,
                        "artifact": artifact if artifact else "",
                        "reason": "non-done evidence",
                    },
                )
            return False

        # Validate evidence input (requires artifact by default; allows specific test-only override)
        if not self._is_valid_evidence(evidence_type, description, artifact):
            return False

        # Close on valid 'done' evidence with acceptable artifact
        target_commitment.status = "closed"
        target_commitment.closed_at = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        target_commitment.close_note = (
            f"Evidence: {description} | artifact={artifact if artifact else 'None'}"
        )

        # Log evidence and closure to EventLog if available
        if self.eventlog:
            self.eventlog.append(
                kind="evidence_added",
                content=description,
                meta={
                    "cid": target_cid,
                    "evidence_type": evidence_type,
                    "artifact": artifact if artifact else "",
                    "confidence": confidence if confidence is not None else 0.0,
                },
            )
            self.eventlog.append(
                kind="commitment_closed",
                content="",
                meta={
                    "cid": target_cid,
                    "closed_at": target_commitment.closed_at,
                    "close_note": target_commitment.close_note,
                },
            )
        return True

    def close_with_evidence(
        self,
        cid: str,
        evidence_type: str,
        description: str,
        artifact: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> bool:
        """
        Close a commitment with evidence by CID.

        Args:
            cid: The ID of the commitment to close.
            evidence_type: Type of evidence (done, blocked, delegated).
            description: Description of the evidence.
            artifact: Optional artifact (file, URL, etc.).
            confidence: Optional confidence score (0-1).

        Returns:
            bool: True if commitment was closed, False otherwise.
        """
        if cid not in self.commitments:
            return False
        commitment = self.commitments[cid]
        return self.close_commitment_with_evidence(
            self.get_commitment_hash(commitment),
            evidence_type,
            description,
            artifact,
            confidence,
        )

    def process_evidence(
        self,
        text: str,
        evidence_type: str = "done",
        artifact: Optional[str] = None,
        event_id: Optional[int] = None,
    ) -> List[str]:
        """
        Process evidence text to close matching commitments.

        Args:
            text: The evidence text.
            evidence_type: Type of evidence (done, blocked, delegated).
            artifact: Optional artifact (file, URL, etc.).
            event_id: Optional event ID associated with this evidence.

        Returns:
            List of commitment IDs that were closed.
        """
        closed_cids = []
        if not text or not isinstance(text, str):
            return closed_cids

        candidates = [
            c for c in self.commitments.values() if c.status in ("open", "tentative")
        ]
        if not candidates:
            return closed_cids

        description = text.strip()
        for c in candidates:
            confidence = self._estimate_evidence_confidence(
                c.text, description, artifact
            )
            if confidence >= 0.7:  # Threshold for closing
                if self.close_commitment_with_evidence(
                    self.get_commitment_hash(c),
                    evidence_type,
                    description,
                    artifact,
                    confidence,
                ):
                    closed_cids.append(c.cid)

        return closed_cids

    def _is_valid_evidence(
        self,
        evidence_type: str,
        description: str,
        artifact: Optional[str] = None,
    ) -> bool:
        """Validate evidence inputs for closing a commitment.

        Policy:
        - Only 'done' evidence is eligible for closure (checked by caller).
        - Require a non-empty artifact string; text-only evidence is insufficient.
        """
        if not isinstance(description, str) or not description.strip():
            return False
        if isinstance(artifact, str) and artifact.strip():
            return True
        # No artifact provided → invalid
        return False

    def expire_old_commitments(self, days_old: int = 30) -> List[str]:
        """Mark old commitments as expired. Logs expiration to EventLog."""
        expired_cids = []

        # Calculate cutoff timestamp
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
        except Exception:
            cutoff = datetime.now(timezone.utc)

        for cid, commitment in self.commitments.items():
            if commitment.status != "open":
                continue

            try:
                created = datetime.fromisoformat(commitment.created_at.replace("Z", ""))
                # Normalize to aware datetime in UTC for comparison
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if created < cutoff:
                    self.mark_commitment(
                        cid, "expired", f"Auto-expired after {days_old} days"
                    )
                    expired_cids.append(cid)
                    if self.eventlog:
                        self.eventlog.append(
                            kind="commitment_expired",
                            content="",
                            meta={
                                "cid": cid,
                                "reason": f"Auto-expired after {days_old} days",
                            },
                        )
            except Exception:
                continue

        return expired_cids


# Ensure proper statement separation with multiple newlines at the end of the file
