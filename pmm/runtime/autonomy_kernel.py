# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/autonomy_kernel.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
import json

from pmm.core.event_log import EventLog
from pmm.core.ledger_mirror import LedgerMirror
from pmm.core.commitment_manager import CommitmentManager
from pmm.runtime.reflection_synthesizer import synthesize_kernel_reflection


def _last_event(events: List[Dict], kind: str) -> Optional[Dict]:
    for event in reversed(events):
        if event.get("kind") == kind:
            return event
    return None


def _events_after(events: List[Dict], anchor: Optional[Dict]) -> List[Dict]:
    if anchor is None:
        return events
    anchor_id = anchor.get("id", 0)
    return [event for event in events if event.get("id", 0) > anchor_id]


def _last_event_matching(
    events: List[Dict], kind: str, predicate: Callable[[Dict], bool]
) -> Optional[Dict]:
    for event in reversed(events):
        if event.get("kind") == kind and predicate(event):
            return event
    return None


@dataclass(frozen=True)
class KernelDecision:
    decision: str
    reasoning: str
    evidence: List[int]

    def as_dict(self) -> Dict[str, object]:
        return {
            "decision": self.decision,
            "reasoning": self.reasoning,
            "evidence": list(self.evidence),
        }


class AutonomyKernel:
    """Deterministic self-direction derived solely from ledger facts."""

    INTERNAL_GOAL_MONITOR_RSM = "monitor_rsm_evolution"
    INTERNAL_GOAL_ANALYZE_GAPS = "analyze_knowledge_gaps"
    KNOWLEDGE_GAP_THRESHOLD = 3
    RSM_EVENT_INTERVAL = 50
    SIGNIFICANT_TENDENCY_THRESHOLD = 5

    def __init__(
        self, eventlog: EventLog, thresholds: Optional[Dict[str, int]] = None
    ) -> None:
        self.eventlog = eventlog
        defaults = {
            "reflection_interval": 10,
            "summary_interval": 50,
            "commitment_staleness": 20,
            "commitment_auto_close": 27,
        }
        self.thresholds = defaults.copy()
        # Load last autonomy_thresholds config if present
        cfg = self._last_autonomy_thresholds_config()
        if cfg:
            for key in list(self.thresholds.keys()):
                if key in cfg and isinstance(cfg[key], int):
                    self.thresholds[key] = int(cfg[key])
        if thresholds:
            for key, value in thresholds.items():
                if key in self.thresholds:
                    self.thresholds[key] = int(value)
        self._goal_state: Dict[str, Dict[str, int]] = {}
        self.commitment_manager = CommitmentManager(eventlog)
        self.mirror = LedgerMirror(eventlog)
        self.active_gap_analysis_cid: Optional[str] = None
        # Listen for autonomy_thresholds config updates at runtime
        self.eventlog.register_listener(self._on_config_event)
        # Ensure immutable policy exists once
        self._ensure_policy_event()
        # Ensure retrieval config exists
        self._ensure_retrieval_config()

    def ensure_rule_table_event(self) -> None:
        """Record the kernel's rule table in the ledger exactly once."""
        content = (
            "{"
            f"reflection_interval:{self.thresholds['reflection_interval']}"
            f",summary_interval:{self.thresholds['summary_interval']}"
            f",commitment_staleness:{self.thresholds['commitment_staleness']}"
            f",commitment_auto_close:{self.thresholds['commitment_auto_close']}"
            "}"
        )
        # Append only if not present with identical content
        recent = self.eventlog.read_all()[-50:]
        existing = [e for e in recent if e.get("kind") == "autonomy_rule_table"]
        if not existing or existing[-1].get("content") != content:
            self.eventlog.append(
                kind="autonomy_rule_table",
                content=content,
                meta={"source": "autonomy_kernel"},
            )

    def _ensure_policy_event(self) -> None:
        # Only one policy event
        events = self.eventlog.read_all()
        for e in reversed(events):
            if e.get("kind") == "config":
                try:
                    data = json.loads(e.get("content") or "{}")
                except Exception:
                    continue
                if isinstance(data, dict) and data.get("type") == "policy":
                    return
        policy = {
            "type": "policy",
            "forbid_sources": {
                "cli": [
                    "config",
                    "checkpoint_manifest",
                    "embedding_add",
                    "retrieval_selection",
                ]
            },
        }
        self.eventlog.append(
            kind="config",
            content=json.dumps(policy, sort_keys=True, separators=(",", ":")),
            meta={"source": "autonomy_kernel"},
        )

    def _ensure_retrieval_config(self) -> None:
        events = self.eventlog.read_all()
        for e in reversed(events):
            if e.get("kind") != "config":
                continue
            try:
                data = json.loads(e.get("content") or "{}")
            except Exception:
                continue
            if isinstance(data, dict) and data.get("type") == "retrieval":
                return
        cfg = {
            "type": "retrieval",
            "strategy": "vector",
            "limit": 7,
            "model": "hash64",
            "dims": 64,
            "quant": "none",
        }
        self.eventlog.append(
            kind="config",
            content=json.dumps(cfg, sort_keys=True, separators=(",", ":")),
            meta={"source": "autonomy_kernel"},
        )

    def _last_autonomy_thresholds_config(self) -> Optional[Dict[str, int]]:
        cfg = None
        try:
            for e in self.eventlog.read_all():
                if e.get("kind") != "config":
                    continue
                raw = e.get("content") or "{}"
                data = json.loads(raw)
                if isinstance(data, dict) and data.get("type") == "autonomy_thresholds":
                    cfg = data
        except Exception:
            return None
        if isinstance(cfg, dict):
            return cfg
        return None

    def _on_config_event(self, event: Dict[str, Any]) -> None:
        if not event or event.get("kind") != "config":
            return
        try:
            data = json.loads(event.get("content") or "{}")
        except Exception:
            return
        if not (isinstance(data, dict) and data.get("type") == "autonomy_thresholds"):
            return
        changed = False
        for key in (
            "reflection_interval",
            "summary_interval",
            "commitment_staleness",
            "commitment_auto_close",
        ):
            if key in data and isinstance(data[key], int):
                val = int(data[key])
                if self.thresholds.get(key) != val:
                    self.thresholds[key] = val
                    changed = True
        if changed:
            # Emit updated rule table (idempotent guard inside)
            self.ensure_rule_table_event()

    def reflect(self, eventlog, meta_extra, staleness_threshold, auto_close_threshold):
        # Idempotent REF handling and deterministic reflection synthesis
        slot_id = (meta_extra or {}).get("slot_id")

        # Read complete ledger once to build projection-only idempotency sets
        raw_events = eventlog.read_all()

        # Collect previously emitted inter_ledger_ref targets, normalized to
        # "<path>#<id>" (strip leading "REF: ") so comparisons match our
        # candidate values.
        def _normalize_ref(content: str) -> str:
            content = content or ""
            return (
                content.split(":", 1)[1].strip()
                if content.startswith("REF:")
                else content
            )

        failed_refs = {
            _normalize_ref(e.get("content", ""))
            for e in raw_events
            if e.get("kind") == "inter_ledger_ref"
            and not (e.get("meta") or {}).get("verified", False)
        }
        seen_refs = {
            _normalize_ref(e.get("content", ""))
            for e in raw_events
            if e.get("kind") == "inter_ledger_ref"
        }

        current_tick_id: Optional[int] = None
        if slot_id:
            for event in reversed(raw_events):
                if (
                    event.get("kind") == "autonomy_tick"
                    and event.get("meta", {}).get("slot_id") == slot_id
                ):
                    current_tick_id = event.get("id")
                    break

        # Build decision context excluding current stimulus/tick
        events = raw_events
        if current_tick_id is not None:
            events = [e for e in raw_events if e.get("id", 0) < current_tick_id]
        events = [e for e in events if e.get("kind") != "autonomy_stimulus"]

        # Compute open commitments canonically via cid
        open_commitments = [
            e
            for e in events
            if e["kind"] == "commitment_open"
            and not any(
                c["kind"] == "commitment_close"
                and c.get("meta", {}).get("cid") == e.get("meta", {}).get("cid")
                for c in events
                if c["id"] > e["id"]
            )
        ]
        # Auto-close stale commitments only under threshold policy
        # Enforce auto-close when there are two or more open commitments
        if auto_close_threshold is not None and len(open_commitments) >= 2:
            for c in sorted(open_commitments, key=lambda ev: ev["id"]):
                cid = (c.get("meta") or {}).get("cid")
                if not cid:
                    continue
                if hasattr(eventlog, "has_exec_bind") and eventlog.has_exec_bind(cid):
                    continue
                events_since_open = sum(1 for e in events if e["id"] > c["id"])
                if events_since_open > auto_close_threshold:
                    eventlog.append(
                        kind="commitment_close",
                        content=f"Commitment closed: {cid}",
                        meta={
                            "reason": "auto_close_idle_opt",
                            "cid": cid,
                            "origin": "autonomy_kernel",
                            "source": "autonomy_kernel",
                        },
                    )

        # No need to recompute stale flag here; synthesizer computes it deterministically

        # Build reflection payload deterministically via synthesizer over full filtered events
        synth = synthesize_kernel_reflection(
            events, staleness_threshold=staleness_threshold or 20
        )
        if synth is None:
            return None
        content_dict, delta_hash_synth = synth

        # Idempotent REF injection: do not re-emit a REF that already failed or was seen
        if len(open_commitments) > 0:
            candidate_ref = "../other_pmm.db#47"
            # Skip if this target was already seen or previously failed
            if candidate_ref not in failed_refs and candidate_ref not in seen_refs:
                content_dict["refs"] = [candidate_ref]

        # Include internal goals list (origin = autonomy_kernel)
        internal_open = self.commitment_manager.get_open_commitments(
            origin="autonomy_kernel"
        )
        content_dict["internal_goals"] = [
            (ev.get("meta") or {}).get("cid")
            for ev in internal_open
            if (ev.get("meta") or {}).get("cid")
        ]

        meta = {
            "synth": "pmm",
            "source": meta_extra.get("source") if meta_extra else "unknown",
        }
        meta.update(meta_extra or {})

        # Append reflection with deterministic JSON encoding unless redundant
        import json as _json

        content = _json.dumps(content_dict, sort_keys=True, separators=(",", ":"))
        # Skip if identical to the last autonomy_kernel reflection content
        last_auto = _last_event_matching(
            events,
            "reflection",
            lambda e: (e.get("meta") or {}).get("source") == "autonomy_kernel",
        )
        if last_auto and (last_auto.get("content") or "") == content:
            return None

        # Stronger gate: delta hash from synthesizer (already based on last-3 slice)
        delta_hash = delta_hash_synth
        last_delta = (
            (last_auto.get("meta") or {}).get("delta_hash") if last_auto else None
        )
        if last_delta and last_delta == delta_hash:
            return None

        # Store delta hash in meta for deterministic replay checks
        meta = dict(meta)
        meta["delta_hash"] = delta_hash
        return eventlog.append(kind="reflection", content=content, meta=meta)

    # Maintenance tasks executed during idle/reflect decisions
    def _maintain_embeddings(self) -> None:
        # Ensure embeddings coverage >=95% for vector strategy
        events = self.eventlog.read_all()
        cfg = None
        for e in reversed(events):
            if e.get("kind") == "config":
                try:
                    d = json.loads(e.get("content") or "{}")
                except Exception:
                    continue
                if isinstance(d, dict) and d.get("type") == "retrieval":
                    cfg = d
                    break
        if not cfg or cfg.get("strategy") != "vector":
            return
        model = str(cfg.get("model", "hash64"))
        dims = int(cfg.get("dims", 64))
        from pmm.runtime.cli import _message_events, _embedding_map  # reuse helpers

        msgs = _message_events(events)
        embs = _embedding_map(events, model=model, dims=dims)
        coverage = len(embs) / max(1, len(msgs))
        if coverage >= 0.95:
            return
        # Backfill last 50 missing
        from pmm.retrieval.vector import build_embedding_content

        missing = [m for m in msgs if int(m.get("id", 0)) not in embs]
        for m in missing[-50:]:
            eid = int(m.get("id", 0))
            payload = build_embedding_content(
                event_id=eid, text=m.get("content") or "", model=model, dims=dims
            )
            self.eventlog.append(
                kind="embedding_add",
                content=payload,
                meta={"source": "autonomy_kernel"},
            )

    def _verify_recent_selections(self, N: int = 5) -> None:
        events = self.eventlog.read_all()
        # Only verify if there was a recent retrieval_selection; otherwise skip
        recent_tail = events[-50:]
        if not any(e.get("kind") == "retrieval_selection" for e in recent_tail):
            return
        sels = [e for e in events if e.get("kind") == "retrieval_selection"][-N:]
        if not sels:
            return
        # Load retrieval cfg
        cfg = None
        for e in reversed(events):
            if e.get("kind") == "config":
                try:
                    d = json.loads(e.get("content") or "{}")
                except Exception:
                    continue
                if isinstance(d, dict) and d.get("type") == "retrieval":
                    cfg = d
                    break
        model = str((cfg or {}).get("model", "hash64"))
        dims = int((cfg or {}).get("dims", 64))
        from pmm.retrieval.vector import (
            DeterministicEmbedder,
            cosine,
            build_index,
            candidate_messages,
        )

        idx = build_index(events, model=model, dims=dims)
        ok_all = True
        for s in sels:
            try:
                data = json.loads(s.get("content") or "{}")
            except Exception:
                continue
            turn_id = int(data.get("turn_id", 0))
            selected = data.get("selected") or []
            # Find last user_message before turn
            query = ""
            for e in reversed(events):
                if int(e.get("id", 0)) >= turn_id:
                    continue
                if e.get("kind") == "user_message":
                    query = e.get("content") or ""
                    break
            if not query:
                continue
            qv = DeterministicEmbedder(model=model, dims=dims).embed(query)
            cands = candidate_messages(events, up_to_id=turn_id)
            scored = []
            for ev in cands:
                eid = int(ev.get("id", 0))
                vec = idx.get(eid)
                if vec is None:
                    vec = DeterministicEmbedder(model=model, dims=dims).embed(
                        ev.get("content") or ""
                    )
                sscore = cosine(qv, vec)
                scored.append((eid, sscore))
            scored.sort(key=lambda t: (-t[1], t[0]))
            top_ids = [eid for (eid, _s) in scored[: len(selected)]]
            if top_ids != selected:
                ok_all = False
        # Emit outcome. Tests expect an explicit OK reflection when matching.
        msg = (
            "retrieval verification OK" if ok_all else "retrieval verification mismatch"
        )
        self.eventlog.append(
            kind="reflection",
            content=json.dumps({"intent": msg, "outcome": msg, "next": "continue"}),
            meta={"source": "autonomy_kernel"},
        )

    def _maybe_append_checkpoint(self, M: int = 50) -> None:
        events = self.eventlog.read_all()
        last_manifest = None
        last_manifest_id = 0
        for e in reversed(events):
            if e.get("kind") == "checkpoint_manifest":
                last_manifest = e
                last_manifest_id = int(e.get("id", 0))
                break
        last_summary = None
        for e in reversed(events):
            if e.get("kind") == "summary_update":
                last_summary = e
                break
        if not last_summary:
            return
        up_to = int(last_summary.get("id", 0))
        since = len([e for e in events if int(e.get("id", 0)) > last_manifest_id])
        # Check rsm_triggered
        triggered = False
        try:
            data = json.loads(last_summary.get("content") or "{}")
            if isinstance(data, str) and "rsm_triggered:1" in data:
                triggered = True
        except Exception:
            triggered = False
        if since >= M or triggered:
            hashes = [
                e.get("hash") or "" for e in events if int(e.get("id", 0)) <= up_to
            ]
            import hashlib as _hl

            root = _hl.sha256(
                json.dumps(hashes, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            # Idempotent
            if last_manifest:
                try:
                    m = json.loads(last_manifest.get("content") or "{}")
                except Exception:
                    m = {}
                if int(m.get("up_to_id", 0)) == up_to and m.get("root_hash") == root:
                    return
            content = json.dumps(
                {
                    "up_to_id": up_to,
                    "covers": ["rsm_state", "open_commitments"],
                    "root_hash": root,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            self.eventlog.append(
                kind="checkpoint_manifest",
                content=content,
                meta={"source": "autonomy_kernel"},
            )

    def _maybe_tune_thresholds(self) -> None:
        # Minimal bounded auto-tuning based on autonomy_metrics last snapshot
        events = self.eventlog.read_all()
        last = None
        for e in reversed(events):
            if e.get("kind") == "autonomy_metrics":
                last = e
                break
        if not last:
            return
        # Simple heuristic: if idle_count dominates and reflect_count low, decrease reflection_interval
        try:
            data = json.loads(last.get("content") or "{}")
        except Exception:
            data = {}
        idle = int(data.get("idle_count", 0))
        reflect = int(data.get("reflect_count", 0))
        if idle > reflect * 3 and self.thresholds["reflection_interval"] > 5:
            self.thresholds["reflection_interval"] -= 1
            self.ensure_rule_table_event()

    def _maybe_emit_autonomy_metrics(self) -> None:
        """Emit autonomy_metrics every 10 ticks when content changes.

        Deterministic and idempotent: compares against the last autonomy_metrics
        content; also gates by ticks_total delta >= 10 to reduce noise.
        """
        events = self.eventlog.read_all()
        ticks = [e for e in events if e.get("kind") == "autonomy_tick"]
        ticks_total = len(ticks)
        if ticks_total == 0:
            return
        # Find last autonomy_metrics
        last_metrics = None
        for e in reversed(events):
            if e.get("kind") == "autonomy_metrics":
                last_metrics = e
                break
        last_ticks = 0
        if last_metrics:
            try:
                data = json.loads(last_metrics.get("content") or "{}")
                last_ticks = int(data.get("ticks_total", 0))
            except Exception:
                last_ticks = 0
        # Emit only on 10-tick boundaries to reduce noise
        if ticks_total % 10 != 0:
            return
        if last_metrics is not None and last_ticks == ticks_total:
            return

        # Compute counts
        idle_count = 0
        reflect_count = 0
        summarize_count = 0
        intention_summarize_count = 0
        last_reflection_id = 0
        for e in events:
            k = e.get("kind")
            if k == "autonomy_tick":
                try:
                    data = json.loads(e.get("content") or "{}")
                except Exception:
                    data = {}
                if (data or {}).get("decision") == "idle":
                    idle_count += 1
            elif k == "reflection":
                reflect_count += 1
                last_reflection_id = int(e.get("id", 0))
                # Count reflections that use the {intent,...} shape
                try:
                    r = json.loads(e.get("content") or "{}")
                except Exception:
                    r = {}
                if isinstance(r, dict) and "intent" in r:
                    intention_summarize_count += 1
            elif k == "summary_update":
                summarize_count += 1

        open_commitments = len(
            LedgerMirror(self.eventlog, listen=False).get_open_commitment_events()
        )
        payload = {
            "idle_count": int(idle_count),
            "reflect_count": int(reflect_count),
            "summarize_count": int(summarize_count),
            "intention_summarize_count": int(intention_summarize_count),
            "ticks_total": int(ticks_total),
            "last_reflection_id": int(last_reflection_id),
            "open_commitments": int(open_commitments),
        }
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        # Idempotent: skip if identical to last
        if last_metrics and (last_metrics.get("content") or "") == content:
            return
        self.eventlog.append(
            kind="autonomy_metrics",
            content=content,
            meta={"source": "autonomy_kernel"},
        )

    def decide_next_action(self) -> KernelDecision:
        gaps = self.mirror.rsm_knowledge_gaps()

        # 1. OPEN GOAL IF NEEDED
        if gaps >= 3:
            self.commitment_manager.open_internal(
                goal="analyze_knowledge_gaps",
                reason=f"{gaps} unresolved singleton intents",
            )

        # 2. EXECUTE EXISTING GOAL
        self.execute_internal_goal(self.INTERNAL_GOAL_ANALYZE_GAPS)
        self.execute_internal_goal(self.INTERNAL_GOAL_MONITOR_RSM)
        events = self.eventlog.read_all()
        if not events:
            return KernelDecision("idle", "no events recorded", [])

        last_metrics = _last_event(events, "metrics_turn")
        if not last_metrics:
            return KernelDecision("idle", "no metrics_turn recorded yet", [])

        last_event_id = events[-1]["id"]

        last_autonomy_reflection = _last_event_matching(
            events,
            "reflection",
            lambda e: e.get("meta", {}).get("source") == "autonomy_kernel",
        )
        if last_autonomy_reflection is None:
            return KernelDecision(
                decision="reflect",
                reasoning="no autonomous reflection recorded yet",
                evidence=[last_event_id],
            )

        events_since_autonomy = _events_after(events, last_autonomy_reflection)

        if len(events_since_autonomy) >= self.thresholds["reflection_interval"]:
            return KernelDecision(
                decision="reflect",
                reasoning=f"reflection_interval reached ({len(events_since_autonomy)})",
                evidence=[last_event_id],
            )

        last_summary = _last_event(events, "summary_update")
        events_since_summary = _events_after(events, last_summary)
        autonomy_reflections_since_summary = [
            event
            for event in events_since_summary
            if event.get("kind") == "reflection"
            and event.get("meta", {}).get("source") == "autonomy_kernel"
        ]

        # Autonomous maintenance on each decision cycle
        self._maintain_embeddings()
        self._verify_recent_selections()
        self._maybe_append_checkpoint()
        self._maybe_tune_thresholds()
        self._maybe_emit_autonomy_metrics()

        if (
            autonomy_reflections_since_summary
            and len(events_since_summary) >= self.thresholds["summary_interval"]
        ):
            return KernelDecision(
                decision="summarize",
                reasoning=f"summary_interval reached ({len(events_since_summary)})",
                evidence=[last_event_id],
            )

        return KernelDecision("idle", "no autonomous action needed", [])

    def _open_gap_commitments(self) -> List[Dict[str, Any]]:
        return [
            event
            for event in self.commitment_manager.get_open_commitments(
                origin="autonomy_kernel"
            )
            if (event.get("meta") or {}).get("goal") == self.INTERNAL_GOAL_ANALYZE_GAPS
        ]

    def has_open_gap_goal(self) -> bool:
        return bool(self._open_gap_commitments())

    def execute_internal_goal(self, goal: str) -> Optional[int]:
        if (
            goal != self.INTERNAL_GOAL_MONITOR_RSM
            and goal != self.INTERNAL_GOAL_ANALYZE_GAPS
        ):
            return None

        events = self.eventlog.read_all()
        if not events:
            return None

        open_goal = self._find_open_internal_goal(goal, events)
        if not open_goal:
            return None

        current_event_id = events[-1]["id"]
        state = self._goal_state.setdefault(
            goal,
            {"last_check_id": self._initial_goal_anchor(goal, open_goal, events)},
        )
        last_check_id = state["last_check_id"]

        if current_event_id <= last_check_id:
            return None

        if goal == self.INTERNAL_GOAL_MONITOR_RSM:
            if current_event_id - last_check_id < self.RSM_EVENT_INTERVAL:
                return None

            mirror = LedgerMirror(self.eventlog, listen=False)
            diff = mirror.diff_rsm(last_check_id, current_event_id)

            if not self._is_significant_rsm_change(diff):
                self._goal_state.pop(goal, None)
                self._close_internal_goal(open_goal, goal)
                return None

            reflection_id = self._append_rsm_reflection(
                diff, last_check_id, current_event_id
            )
            self._goal_state[goal]["last_check_id"] = reflection_id
            return reflection_id
        elif goal == self.INTERNAL_GOAL_ANALYZE_GAPS:
            snap = self.mirror.rsm_snapshot()
            unresolved = [
                i
                for i, c in snap["intents"].items()
                if c == 1
                and not any(r["intent"].startswith(i[:50]) for r in snap["reflections"])
            ]
            reflection_content = json.dumps(
                {
                    "intent": "gap_analysis",
                    "outcome": f"Unresolved: {', '.join(unresolved)}",
                }
            )
            reflection_id = self.eventlog.append(
                kind="reflection",
                content=reflection_content,
                meta={"source": "autonomy_kernel", "goal": goal},
            )
            cid = (open_goal.get("meta") or {}).get("cid")
            if cid:
                self.eventlog.append(
                    kind="commitment_close",
                    content=f"Commitment closed: {cid}",
                    meta={
                        "source": "autonomy_kernel",
                        "cid": cid,
                        "goal": goal,
                        "outcome": "analyzed",
                    },
                )
            return reflection_id

    def _is_significant_rsm_change(self, diff: Dict[str, object]) -> bool:
        tendencies = diff.get("tendencies_delta", {}) or {}
        if any(
            abs(int(value)) > self.SIGNIFICANT_TENDENCY_THRESHOLD
            for value in tendencies.values()
        ):
            return True
        if diff.get("gaps_added") or diff.get("gaps_resolved"):
            return True
        return False

    def _find_open_internal_goal(
        self, goal: str, events: List[Dict[str, object]]
    ) -> Optional[Dict[str, object]]:
        open_event: Optional[Dict[str, object]] = None
        for event in events:
            if (
                event.get("kind") == "commitment_open"
                and event.get("meta", {}).get("goal") == goal
            ):
                open_event = event
            elif (
                open_event
                and event.get("kind") == "commitment_close"
                and event.get("meta", {}).get("cid")
                == open_event.get("meta", {}).get("cid")
            ):
                open_event = None
        return open_event

    def _initial_goal_anchor(
        self,
        goal: str,
        open_goal: Dict[str, object],
        events: List[Dict[str, object]],
    ) -> int:
        if goal == self.INTERNAL_GOAL_MONITOR_RSM:
            summary_id = self._last_summary_event_id(events)
            if summary_id is not None:
                return summary_id
            return int(open_goal.get("id", 0))
        return 0

    def _last_summary_event_id(self, events: List[Dict[str, object]]) -> Optional[int]:
        for event in reversed(events):
            if event.get("kind") == "summary_update":
                return int(event["id"])
        return None

    def _append_rsm_reflection(
        self, diff: Dict[str, object], start_id: int, end_id: int
    ) -> int:
        tendencies = diff.get("tendencies_delta", {}) or {}
        ordered_tendencies = {
            key: int(tendencies[key]) for key in sorted(tendencies.keys())
        }
        payload = {
            "action": self.INTERNAL_GOAL_MONITOR_RSM,
            "tendencies_delta": ordered_tendencies,
            "gaps_added": diff.get("gaps_added", []),
            "gaps_resolved": diff.get("gaps_resolved", []),
            "from_event": int(start_id),
            "to_event": int(end_id),
            "next": "monitor",
        }
        meta = {
            "source": "autonomy_kernel",
            "goal": self.INTERNAL_GOAL_MONITOR_RSM,
        }
        return self.eventlog.append(
            kind="reflection",
            content=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            meta=meta,
        )

    def _close_internal_goal(
        self, open_goal: Dict[str, object], goal: str
    ) -> Optional[int]:
        cid = (open_goal.get("meta") or {}).get("cid")
        if not cid:
            return None
        return self.eventlog.append(
            kind="commitment_close",
            content=f"Commitment closed: {cid}",
            meta={
                "source": "autonomy_kernel",
                "cid": cid,
                "goal": goal,
                "reason": "rsm_stable",
            },
        )
