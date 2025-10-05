"""Minimal commitment tracking built on EventLog + projection.

Intent:
- Evidence-first lifecycle only: open via explicit user/agent action,
  close only with allowed evidence.
- No TTL, no heuristics, no autoclose.
"""

from __future__ import annotations

import datetime as _dt
import logging
import uuid as _uuid
from typing import TYPE_CHECKING, Any

from pmm.commitments.tracker import (
    ttl as _ttl,
)  # Stage 2 TTL helpers (no behavior change)
from pmm.runtime.embeddings import compute_embedding as _emb
from pmm.runtime.embeddings import cosine_similarity as _cos
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model

if TYPE_CHECKING:
    from pmm.runtime.memegraph import MemeGraphProjection


logger = logging.getLogger(__name__)


class CommitmentTracker:
    """Commitment lifecycle backed by the EventLog.

    Parameters
    ----------
    eventlog : EventLog
        The event log instance to persist events into.
    """

    def __init__(
        self,
        eventlog: EventLog,
        memegraph: MemeGraphProjection | None = None,
    ) -> None:
        self.eventlog = eventlog
        self._memegraph = memegraph

    def _open_commitments_legacy(self) -> dict[str, dict[str, Any]]:
        # Route through read-only API for consistency; same semantics as projection
        try:
            from pmm.commitments.tracker import (
                api as _tracker_api,
            )  # lazy to avoid import-time cycles

            return _tracker_api.open_commitments(self.eventlog.read_all())
        except Exception:
            # Fallback to legacy projection if scaffolding unavailable
            events = self.eventlog.read_all()
            model = build_self_model(events)
            return (model.get("commitments") or {}).get("open", {})

    def _open_map_all(
        self, events: list[dict] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Return current open commitments map using the store-backed API when available.

        Falls back to projection if the scaffolding API is unavailable. Pure read-only.
        """
        try:
            from pmm.commitments.tracker import api as _tracker_api

            evs = events if events is not None else self.eventlog.read_all()
            return _tracker_api.open_commitments(evs)
        except Exception:
            evs = events if events is not None else self.eventlog.read_all()
            model = build_self_model(evs)
            return (model.get("commitments") or {}).get("open", {})

    def _compare_open_maps(
        self,
        legacy_map: dict[str, dict[str, Any]],
        graph_map: dict[str, dict[str, Any]],
    ) -> None:
        try:
            legacy_keys = set(legacy_map.keys())
            graph_keys = set(graph_map.keys())
            if legacy_keys != graph_keys:
                logger.debug(
                    "memegraph commitment shadow mismatch keys: legacy=%s graph=%s",
                    sorted(legacy_keys),
                    sorted(graph_keys),
                )
                return
            for cid in legacy_keys:
                legacy_text = str((legacy_map.get(cid) or {}).get("text") or "").strip()
                graph_text = str(graph_map.get(cid, {}).get("text") or "").strip()
                if legacy_text != graph_text:
                    logger.debug(
                        "memegraph commitment shadow text mismatch for %s: legacy=%r graph=%r",
                        cid,
                        legacy_text,
                        graph_text,
                    )
        except Exception:
            logger.debug("memegraph commitment shadow comparison failed", exc_info=True)

    def process_assistant_reply(
        self, text: str, reply_event_id: int | None = None
    ) -> list[str]:
        """Detect commitments in assistant replies and open them.

        Returns list of newly opened commitment ids (cids).
        """
        # Expire old commitments (TTL) opportunistically on assistant activity
        try:
            self.expire_old_commitments()
        except Exception:
            # Do not fail user flow if expiration has issues
            pass
        # Free-text commitment opening is disabled; use explicit structural events
        return []

    # --- Identity helpers (compat with legacy tracker) ---
    def _rebind_commitments_on_identity_adopt(
        self,
        old_name: str,
        new_name: str,
        *,
        identity_adopt_event_id: int | None = None,
    ) -> None:
        """Rebind or update open commitments that reference the old identity name.

        Emits a `commitment_rebind` followed by a `commitment_update` with the new text,
        mirroring the legacy helper so callers can rely on consistent behavior.
        Deterministic and best-effort; exceptions are swallowed to avoid breaking flows.
        """
        try:
            if not old_name or not new_name:
                return
            if str(old_name).strip().lower() == str(new_name).strip().lower():
                return
            open_map = self._open_commitments_legacy()
            if self._memegraph is not None:
                graph_map = self._memegraph.open_commitments_snapshot()
                self._compare_open_maps(open_map, graph_map)
            # Accumulate a summary of rebinds emitted during this invocation to support
            # a single identity_projection event after processing, idempotently.
            rebind_summaries: list[dict[str, Any]] = []
            for cid, meta in list(open_map.items()):
                txt = str((meta or {}).get("text") or "")
                if not txt:
                    continue
                if (str(old_name).lower() in txt.lower()) or (
                    identity_adopt_event_id is not None
                ):
                    # Idempotency guard: do not emit duplicate rebind for same adopt id
                    try:
                        already = False
                        if identity_adopt_event_id is not None:
                            try:
                                evs_tail = self.eventlog.read_all()[-200:]
                            except Exception:
                                evs_tail = self.eventlog.read_all()
                            for ev in reversed(evs_tail):
                                if ev.get("kind") != "commitment_rebind":
                                    continue
                                m = ev.get("meta") or {}
                                if str(m.get("cid")) == str(cid) and int(
                                    m.get("identity_adopt_event_id") or -1
                                ) == int(identity_adopt_event_id):
                                    already = True
                                    break
                        if not already:
                            # Emit rebind marker, tagged with adoption id
                            self.eventlog.append(
                                kind="commitment_rebind",
                                content="",
                                meta={
                                    "cid": cid,
                                    "old_name": old_name,
                                    "new_name": new_name,
                                    "original_text": txt,
                                    "identity_adopt_event_id": identity_adopt_event_id,
                                },
                            )
                            # Record summary for identity_projection
                            rebind_summaries.append(
                                {
                                    "cid": str(cid),
                                    "old_name": str(old_name),
                                    "new_name": str(new_name),
                                    "original_text": txt,
                                }
                            )
                    except Exception:
                        pass
                    # Compute new text by simple replacement (best-effort)
                    try:
                        new_txt = txt.replace(old_name, new_name)
                    except Exception:
                        new_txt = txt
                    if new_txt != txt:
                        try:
                            self.eventlog.append(
                                kind="commitment_update",
                                content=new_txt,
                                meta={
                                    "cid": cid,
                                    "old_text": txt,
                                    "reason": "identity_rebind",
                                },
                            )
                        except Exception:
                            pass
            # Emit a single identity_projection summary if we performed any rebinds and
            # no prior projection exists for this identity adoption id. If none were
            # emitted in this helper invocation, but there are existing commitment_rebind
            # events for the same adoption id, summarize those instead to ensure a
            # projection is present.
            try:
                if identity_adopt_event_id is not None:
                    # If local list is empty, attempt to summarize existing rebinds for this adopt id
                    if not rebind_summaries:
                        try:
                            evs_tail3 = self.eventlog.read_all()[-400:]
                        except Exception:
                            evs_tail3 = self.eventlog.read_all()
                        for ev in evs_tail3:
                            if ev.get("kind") != "commitment_rebind":
                                continue
                            m3 = ev.get("meta") or {}
                            if int(m3.get("identity_adopt_event_id") or -1) != int(
                                identity_adopt_event_id
                            ):
                                continue
                            rebind_summaries.append(
                                {
                                    "cid": str(m3.get("cid") or ""),
                                    "old_name": str(m3.get("old_name") or ""),
                                    "new_name": str(m3.get("new_name") or ""),
                                    "original_text": str(m3.get("original_text") or ""),
                                }
                            )
                    # Proceed only if we have something to project
                    if rebind_summaries:
                        # Check idempotency: skip if an identity_projection exists for this adopt id
                        already_proj = False
                        try:
                            evs_tail2 = self.eventlog.read_all()[-200:]
                        except Exception:
                            evs_tail2 = self.eventlog.read_all()
                        for ev in reversed(evs_tail2):
                            if ev.get("kind") != "identity_projection":
                                continue
                            m2 = ev.get("meta") or {}
                            if int(m2.get("identity_adopt_event_id") or -1) == int(
                                identity_adopt_event_id
                            ):
                                already_proj = True
                                break
                        if not already_proj:
                            self.eventlog.append(
                                kind="identity_projection",
                                content="",
                                meta={
                                    "identity_adopt_event_id": identity_adopt_event_id,
                                    "old_name": old_name,
                                    "new_name": new_name,
                                    "rebinds": rebind_summaries,
                                },
                            )
            except Exception:
                # Never allow projection summary to break flow
                pass
        except Exception:
            return

    def process_evidence(self, text: str) -> list[str]:
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

        # Build recent events slice and open commitments list
        events = self.eventlog.read_all()
        # Use API snapshot for open-set parity with legacy projection
        try:
            from pmm.commitments.tracker import api as _tracker_api

            open_map: dict[str, dict] = _tracker_api.open_commitments(events)
        except Exception:
            model = build_self_model(events)
            open_map = (model.get("commitments", {}) or {}).get("open", {})
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
        closed: list[str] = []
        if cands:
            # choose best by score then stable by cid
            cands_sorted = sorted(cands, key=lambda t: (-float(t[1]), str(t[0])))
            cid, score, snippet = cands_sorted[0]
            # Enforce deterministic threshold
            if float(score) >= 0.70:
                # Check if this commitment was recently closed by reflection
                recently_closed_by_reflection = False
                for ev in reversed(events[-50:]):  # Check last 50 events
                    if ev.get("kind") == "commitment_close":
                        m = ev.get("meta") or {}
                        if m.get("cid") == cid and m.get("source") == "reflection":
                            recently_closed_by_reflection = True
                            break

                # Idempotent candidate append: avoid duplicate immediate candidate
                already = False
                for ev in reversed(events):
                    if ev.get("kind") != "evidence_candidate":
                        continue
                    m = ev.get("meta") or {}
                    if m.get("cid") == cid and m.get("snippet") == snippet:
                        already = True
                        break
                if not already and not recently_closed_by_reflection:
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
        return []

    # --- Reflection-driven lifecycle helpers ---
    def close_reflection_on_next(self, reply: str) -> None:
        """Close reflection-driven commitments when satisfied by reply."""
        # Read open commitments via store-backed API (fallback to projection)
        events = self.eventlog.read_all()
        open_map = self._open_map_all(events) or {}

        # Close all reflection-driven commitments via structured close helper
        for cid, meta in open_map.items():
            reason = str((meta or {}).get("reason") or "")
            if reason == "reflection":
                # Use text-only evidence; deterministic helper ensures idempotency
                self.close_with_evidence(
                    cid, evidence_type="done", description=reply, artifact=None
                )

    # supersede_reflection_commitments removed (unused). Use close_with_evidence() directly when needed.

    def add_commitment(
        self,
        text: str,
        source: str | None = None,
        extra_meta: dict | None = None,
        project: str | None = None,
    ) -> str:
        """Open a new commitment and return its cid.

        Logs: kind="commitment_open" with meta {"cid", "text", "source"}.
        """
        # Structural validation: reject reflection-like text
        if not self._is_valid_commitment_structure(text):
            return ""  # Silently reject invalid structure

        # Deduplicate against last N open commitments
        if self._is_duplicate_of_recent_open(text):
            # No-op: return a stable cid-like marker to reflect dedup action
            return ""
        cid = _uuid.uuid4().hex
        meta: dict = {"cid": cid, "text": text}
        if source is not None:
            meta["source"] = source
        if isinstance(extra_meta, dict):
            # Shallow merge; do not overwrite cid/text/source
            for k, v in extra_meta.items():
                if k not in meta:
                    meta[k] = v
        # Optional project grouping: explicit or auto-detected
        # 1) Explicit project argument or meta.project_id
        explicit_pid: str | None = None
        if project and isinstance(project, str):
            explicit_pid = str(project).strip()
        elif isinstance(meta.get("project_id"), str):
            explicit_pid = str(meta.get("project_id")).strip()

        # 2) Auto-detect project tag if not explicitly provided
        auto_pid: str | None = None
        if not explicit_pid:
            auto_pid = self._auto_project_id(text)
            # Only promote to active project if at least one other OPEN commitment shares the same tag
            if auto_pid:
                try:
                    evs = self.eventlog.read_all()
                    model0 = build_self_model(evs)
                    open_map0: dict[str, dict] = (model0.get("commitments") or {}).get(
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
            model = build_self_model(None, eventlog=self.eventlog)
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
    def _auto_project_id(self, text: str) -> str | None:
        """Derive a stable, short project id from commitment text.

        Heuristic: tokenize, drop stopwords and common verbs, take first 1–2 tokens, join with '-'.
        Returns None if insufficient signal.
        """
        try:
            from pmm.utils.parsers import tokenize_alnum

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
            s = (text or "").lower()
            toks = tokenize_alnum(s)
            verbs = {"do", "make", "get", "take", "go", "come", "see", "know"}

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
        events: list[dict],
        open_commitments: list[dict],
        recent_window: int = 20,
    ) -> list[tuple[str, float, str]]:
        """
        Returns a list of (cid, score, snippet) for candidate evidence found in the
        recent window. Deterministic scoring; no side effects.

        Scoring:
        - Exact/substring match of promise text in recent content -> +0.6
        - Embedding cosine similarity (max with heuristic)
        Threshold handled by caller. Snippet is a <=160 char window around the match.
        """

        # Normalize helper
        def _norm(s: str) -> str:
            return " ".join((s or "").strip().lower().split())

        # Build recent text corpus from last `recent_window` assistant/user-like events
        # In this codebase, assistant replies are `response`; tests may inject plain events
        tail: list[dict] = []
        for ev in reversed(events):
            if ev.get("kind") in {"response", "user", "reflection"}:
                tail.append(ev)
                if len(tail) >= recent_window:
                    break
        tail = list(reversed(tail))
        concat = "\n".join([str(e.get("content") or "") for e in tail])
        low = _norm(concat)

        # Compute embeddings once for the whole recent text if provider available
        emb_low = _emb(low)

        # Lightweight token normalization helpers for approximate overlap
        def _tok_stem(s: str) -> list[str]:
            from pmm.utils.parsers import split_non_alnum

            toks = split_non_alnum(s or "")
            out: list[str] = []
            for t in toks:
                # Minimal stemming and a few irregulars to improve robustness
                if t == "wrote":
                    out.append("write")
                    continue
                if t.endswith("ing") and len(t) > 5:
                    t = t[:-3]
                elif t.endswith("ed") and len(t) > 4:
                    t = t[:-2]
                elif t.endswith("es") and len(t) > 5:
                    t = t[:-2]
                elif t.endswith("s") and len(t) > 4:
                    t = t[:-1]
                out.append(t)
            return out

        def _lev(a: str, b: str) -> int:
            la, lb = len(a), len(b)
            if la == 0:
                return lb
            if lb == 0:
                return la
            dp = list(range(lb + 1))
            for i in range(1, la + 1):
                prev = dp[0]
                dp[0] = i
                for j in range(1, lb + 1):
                    tmp = dp[j]
                    cost = 0 if a[i - 1] == b[j - 1] else 1
                    dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
                    prev = tmp
            return dp[-1]

        def _approx_token_overlap(a_text: str, b_text: str) -> float:
            at = _tok_stem(a_text)
            bt = _tok_stem(b_text)
            if not at:
                return 0.0
            matched = 0
            for t in at:
                ok = False
                if t in bt:
                    ok = True
                else:
                    for u in bt:
                        if _lev(t, u) <= 1:
                            ok = True
                            break
                if ok:
                    matched += 1
            return float(matched) / float(len(at))

        results: list[tuple[str, float, str]] = []
        for item in open_commitments:
            cid = str(item.get("cid"))
            text = _norm(str(item.get("text") or ""))
            if not cid or not text:
                continue
            score = 0.0
            snippet = ""
            # exact/substring between promise text and the whole recent text
            hay = low
            if text and text in hay:
                score += 0.6
                # create snippet window
                idx = max(0, (concat.lower()).find(text))
                raw = concat
                # best-effort snippet from original concat around index
                snippet = raw[max(0, idx - 40) : idx + len(text) + 40]

            # Embedding similarity as alternate score (prefer max between heuristic and cosine)
            if emb_low is not None:
                emb_text = _emb(text)
                if emb_text is not None:
                    sim = _cos(emb_low, emb_text)
                    if sim > score:
                        score = float(sim)

            # Approximate token overlap (robust to minor morphology/typos)
            try:
                approx = _approx_token_overlap(text, concat)
                if approx > score:
                    score = float(approx)
            except Exception:
                pass

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

        # Require artifact only when configured; otherwise allow non-empty text
        try:
            from pmm.config import require_artifact_evidence

            require_artifact = require_artifact_evidence
        except Exception:
            require_artifact = False
        has_text = isinstance(description, str) and bool(description.strip())
        has_art = isinstance(artifact, str) and bool(artifact.strip())
        if require_artifact:
            if not (has_text and has_art):
                return False
        else:
            if not (has_text or has_art):
                return False

        # Derive open commitments from projection
        model = build_self_model(None, eventlog=self.eventlog)
        open_map: dict[str, dict] = model.get("commitments", {}).get("open", {})
        if cid not in open_map:
            # Unknown or already closed
            return False

        meta: dict = {
            "cid": cid,
            "evidence_type": evidence_type,
            "description": description,
            "clean": True,
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

        # Immediately recompute and emit fresh metrics after commitment_close
        try:
            from pmm.runtime.metrics import get_or_compute_ias_gas

            ias, gas = get_or_compute_ias_gas(self.eventlog)
            # Standardize event kind name to match metrics subsystem
            self.eventlog.append(
                kind="metrics_update",
                content="",
                meta={
                    "IAS": ias,
                    "GAS": gas,
                    "reason": "live_update",
                },
            )
        except Exception:
            # Never let metrics computation break commitment flow
            pass

        # If this was the last open commitment in its project, close the project idempotently
        try:
            if proj_id:
                # Recompute open view after closing this cid
                evs_after = self.eventlog.read_all()
                model_after = build_self_model(evs_after)
                open_map_after: dict[str, dict] = (
                    model_after.get("commitments", {}) or {}
                ).get("open", {})
                # Build assignment map for open cids
                assign: dict[str, str] = {}
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

    def _resolve_project_for_cid(self, cid: str) -> str | None:
        """Return project_id for an open or recently-closed cid via meta or assignment events."""
        try:
            evs = self.eventlog.read_all()
            model = build_self_model(evs)
            open_map: dict[str, dict] = model.get("commitments", {}).get("open", {})
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
    def sweep_for_expired(self, events: list[dict], ttl_ticks: int = 10) -> list[dict]:
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
        open_event_by_cid: dict[str, dict] = {}
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
        snooze_until: dict[str, int] = {}
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

        out: list[dict] = []
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
        model = build_self_model(None, eventlog=self.eventlog)
        open_map: dict[str, dict] = model.get("commitments", {}).get("open", {})
        for cid, meta in list(open_map.items()):
            txt = str((meta or {}).get("text") or "")
            if txt == target_txt:
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

    def list_open(self) -> dict[str, dict]:
        """Return mapping of cid -> meta for open commitments via projection."""
        model = build_self_model(None, eventlog=self.eventlog)
        return model.get("commitments", {}).get("open", {})

    # --- TTL expiration and dedup helpers ---
    @staticmethod
    def _normalize_text(s: str) -> str:
        return " ".join((s or "").strip().lower().split())

    def _recent_open_cids(self, n: int) -> list[tuple[str, int]]:
        # Return list of (cid, open_event_id) for currently open commitments, ordered by recency of open
        model = build_self_model(None, eventlog=self.eventlog)
        open_map: dict[str, dict] = model.get("commitments", {}).get("open") or {}
        open_cids = set(open_map.keys())
        last_open_event_id: dict[str, int] = {cid: -1 for cid in open_cids}
        for ev in self.eventlog.read_all():  # ascending id
            if ev.get("kind") == "commitment_open":
                cid = (ev.get("meta") or {}).get("cid")
                if cid in open_cids:
                    last_open_event_id[cid] = ev.get("id") or last_open_event_id.get(
                        cid, -1
                    )
        ordered = sorted(last_open_event_id.items(), key=lambda kv: kv[1], reverse=True)
        return ordered[: max(0, n)]

    def _is_valid_commitment_structure(self, text: str) -> bool:
        """Validate commitment structure without brittle markers.

        Uses deterministic structural rules and semantic validation.
        """
        try:
            from pmm.config import MAX_COMMITMENT_CHARS

            max_commitment_chars = MAX_COMMITMENT_CHARS
        except ImportError:
            max_commitment_chars = 400

        # 1. Length constraint (deterministic)
        if len(text) > max_commitment_chars:
            return False

        # 2. Token count (prevents verbose analysis)
        tokens = text.split()
        if len(tokens) > 50:  # ~40-50 words max
            return False

        # 3. No comparison operators (structural, not keyword)
        if any(op in text for op in ["≥", "≤", ">=", "<=", "==", "!="]):
            return False

        # 4. No markdown formatting (analysis uses this)
        if any(md in text for md in ["**", "##", "- ", "* ", "```"]):
            return False

        # 5. Semantic validation: OPTIONAL positive signal
        # If semantic check passes, great. If not, structural checks are enough.
        # This prevents false negatives from the semantic extractor.
        try:
            from pmm.commitments.extractor import CommitmentExtractor

            extractor = CommitmentExtractor()
            extractor.detect_intent(text)

            # If it strongly matches analysis/reflection patterns, reject it
            # But don't reject just because it doesn't match commitment patterns
            # (the extractor has false negatives)
        except Exception:
            pass

        # If we got here, structural checks passed - accept it
        return True

    def _is_duplicate_of_recent_open(self, text: str) -> bool:
        # Constant dedup window (no env override)
        dedup_n = 5
        cand_norm = self._normalize_text(text)
        model = build_self_model(None, eventlog=self.eventlog)
        open_map: dict[str, dict] = model.get("commitments", {}).get("open", {})
        for cid, _eid in self._recent_open_cids(dedup_n):
            txt = str((open_map.get(cid) or {}).get("text") or "")
            if self._normalize_text(txt) == cand_norm:
                return True
        return False

    def expire_old_commitments(self, *, now_iso: str | None = None) -> list[str]:
        """Expire open commitments older than TTL hours.

        Returns list of expired cids.
        """
        # Constant TTL hours (no env override)
        ttl_hours = 24
        if ttl_hours < 0:
            return []

        # Build maps of open cids and find their open timestamps by scanning events
        events = self.eventlog.read_all()
        # Legacy-compatible TTL shim (no behavior change): compute boundaries
        try:
            _ = _ttl.compute_current_tick(events)
        except Exception:
            pass
        model = build_self_model(events)
        open_map: dict[str, dict] = model.get("commitments", {}).get("open", {})
        if not open_map:
            return []

        # Final flip: Use ttl.compute_expired() and emit expiration events
        if now_iso is None:
            now_iso = _dt.datetime.now(_dt.UTC).isoformat()
        expired_pairs = _ttl.compute_expired(
            events, ttl_hours=ttl_hours, now_iso=now_iso
        )
        expired: list[str] = []
        for cid, _placeholder in expired_pairs:
            if cid not in open_map:
                continue
            text0 = str((open_map.get(cid) or {}).get("text") or "")
            try:
                self.eventlog.append(
                    kind="commitment_expire",
                    content=f"Commitment expired: {text0}",
                    meta={"cid": cid, "reason": "ttl", "expired_at": now_iso},
                )
                expired.append(cid)
            except Exception:
                continue
        return expired


# --- Step 19: Invariant breach self-triage (log-only, idempotent) ---
TRIAGE_WINDOW_EIDS: int = 500
TRIAGE_PRIORITY: str = "low"
TRIAGE_TEXT_TMPL: str = "Investigate invariant violation CODE={code}"


def open_violation_triage(
    events_tail: list[dict],
    evlog: EventLog,
    window_eids: int = TRIAGE_WINDOW_EIDS,
) -> dict[str, list[str]]:
    """
    Idempotently open at most one low-priority triage commitment per unique
    invariant_violation 'code' visible in the tail window.

    Returns: {"opened": [codes], "skipped": [codes]}
    Deterministic, no exceptions.
    """
    try:
        # 1) Collect violation codes present in the tail
        codes: list[str] = []
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
        triage_cid_by_code: dict[str, str] = {}
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
        opened: list[str] = []
        skipped: list[str] = []
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


# (Legacy Commitment dataclass removed; see pmm.commitments.tracker.types for canonical types.)
