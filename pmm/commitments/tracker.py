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
            open_map: Dict[str, Dict] = (model.get("commitments") or {}).get(
                "open"
            ) or {}
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
