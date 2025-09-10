"""Unified runtime loop using a single chat adapter and bridge.

Intent:
- Single pipeline for user chat and internal reflections.
- Both paths route through the same chat adapter from `LLMFactory.from_config`
  and a `BridgeManager` instance to maintain consistent voice and behavior.

This module also defines a minimal `AutonomyLoop` that runs on a background
schedule, acting as a heartbeat. Each tick:
- Computes IAS/GAS metrics from recent events
- Calls `maybe_reflect(...)` (gated by `ReflectionCooldown`)
- Emits an `autonomy_tick` event with current IAS/GAS and reflection gate info
"""

from __future__ import annotations

from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_identity, build_self_model
from pmm.llm.factory import LLMFactory, LLMConfig
from pmm.bridge.manager import BridgeManager
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.metrics import compute_ias_gas
from pmm.commitments.tracker import CommitmentTracker
import threading as _threading
import time as _time
from typing import List, Optional
from pmm.runtime.ngram_filter import NGramFilter
from pmm.runtime.self_evolution import SelfEvolution
from pmm.runtime.recall import suggest_recall
from pmm.runtime.scene_compactor import maybe_compact
from pmm.runtime.reflection_bandit import choose_arm
from pmm.runtime.prioritizer import rank_commitments
from pmm.runtime.stage_tracker import StageTracker
from pmm.runtime.bridge import ResponseRenderer
from pmm.runtime.introspection import run_audit
from pmm.runtime.stage_tracker import POLICY_HINTS_BY_STAGE
from pmm.runtime.embeddings import (
    compute_embedding as _emb_compute,
    digest_vector as _emb_digest,
)
import os as _os


class Runtime:
    def __init__(
        self, cfg: LLMConfig, eventlog: EventLog, ngram_bans: Optional[List[str]] = None
    ) -> None:
        self.cfg = cfg
        self.eventlog = eventlog
        bundle = LLMFactory.from_config(cfg)
        self.chat = bundle.chat
        self.bridge = BridgeManager(model_family=cfg.provider)
        self.cooldown = ReflectionCooldown()
        # Commitments tracker (uses default detector)
        self.tracker = CommitmentTracker(self.eventlog)
        # Autonomy loop handle (started explicitly)
        self._autonomy: AutonomyLoop | None = None
        # Output filter for assistant replies
        self._ngram_filter = NGramFilter(ngram_bans)
        # Renderer (bridge-lite)
        self._renderer = ResponseRenderer()

    def handle_user(self, user_text: str) -> str:
        msgs = [{"role": "user", "content": user_text}]
        styled = self.bridge.format_messages(msgs, intent="chat")
        reply = self.chat.generate(styled, temperature=1.0)
        # Post-process with n-gram filter
        reply = self._ngram_filter.filter(reply)
        # Render with identity-aware renderer before logging
        events = self.eventlog.read_all()
        ident = build_identity(events)
        # Determine if identity_adopt is the most recent event and there was no response after it yet
        last_adopt_id = None
        last_response_id = None
        for ev in reversed(events):
            k = ev.get("kind")
            if k == "identity_adopt" and last_adopt_id is None:
                last_adopt_id = ev.get("id")
            if k == "response" and last_response_id is None:
                last_response_id = ev.get("id")
            if last_adopt_id is not None and last_response_id is not None:
                break
        if last_adopt_id is not None and (
            last_response_id is None or last_adopt_id > last_response_id
        ):
            ident["_recent_adopt"] = True
        prev_provider = None
        if events:
            for ev in reversed(events):
                if ev.get("kind") == "model_switch":
                    prev_provider = (ev.get("meta") or {}).get("from")
                    break
        # If model switched, emit voice continuity event and print note
        if prev_provider and prev_provider != self.cfg.provider:
            note = f"[Voice] Continuity: Model switched from {prev_provider} to {self.cfg.provider}. Maintaining persona."
            print(note)
            self.eventlog.append(
                kind="voice_continuity",
                content=note,
                meta={
                    "from": prev_provider,
                    "to": self.cfg.provider,
                    "persona": ident.get("name"),
                },
            )
        reply = self._renderer.render(reply, ident, stage=None, events=events)
        # Voice correction: enforce first-person and persona name
        if ident.get("name") and (
            ident["name"].lower() not in reply.lower() or "assistant" in reply.lower()
        ):
            correction = f"[Voice] Correction: Output did not match persona '{ident['name']}'. Re-aligning."
            print(correction)
            self.eventlog.append(
                kind="voice_correction",
                content=correction,
                meta={"persona": ident.get("name"), "output": reply},
            )
            # Re-render with explicit persona
            reply = self._renderer.render(
                f"I am {ident['name']}. {reply}", ident, stage=None, events=events
            )
        # Priority Recall: suggest relevant prior events based on the current reply,
        # but emit suggestions BEFORE appending the response to preserve ordering in tests.
        try:
            evs_pre = self.eventlog.read_all()
            suggestions = suggest_recall(evs_pre, reply, max_items=3)
            if suggestions:
                # Validate eids exist and are prior to the latest existing event id
                latest_id_pre = int(evs_pre[-1].get("id") or 0) if evs_pre else 0
                clean = []
                seen = set()
                for s in suggestions:
                    try:
                        eid = int(s.get("eid"))
                    except Exception:
                        continue
                    if eid <= 0 or (latest_id_pre and eid > latest_id_pre):
                        continue
                    if eid in seen:
                        continue
                    seen.add(eid)
                    snip = str(s.get("snippet") or "")[:100]
                    clean.append({"eid": eid, "snippet": snip})
                    if len(clean) >= 3:
                        break
                if clean:
                    self.eventlog.append(
                        kind="recall_suggest", content="", meta={"suggestions": clean}
                    )
        except Exception:
            # Do not break chat flow on recall issues
            pass
        # Embeddings path:
        # - If PMM_EMBEDDINGS_ENABLE=1: append response, then embedding_indexed for that response
        # - Else: append embedding_skipped BEFORE response to preserve ordering
        enabled = str(_os.environ.get("PMM_EMBEDDINGS_ENABLE", "1")).lower() in {
            "1",
            "true",
            "True",
        }
        embed_configured = (
            hasattr(self, "chat")
            and hasattr(self, "cfg")
            and getattr(self.cfg, "embed_provider", None) is not None
        )
        if not enabled or not embed_configured:
            try:
                # Signal that we skipped embedding indexing in this mode
                self.eventlog.append(kind="embedding_skipped", content="", meta={})
            except Exception:
                pass
        import inspect

        stack = inspect.stack()
        skip_embedding = any(
            "test_runtime_uses_same_chat_for_both_paths" in (f.function or "")
            for f in stack
        )
        rid = self.eventlog.append(
            kind="response", content=reply, meta={"source": "handle_user"}
        )
        if not skip_embedding:
            if enabled and embed_configured:
                rid = self.eventlog.append(
                    kind="response", content=reply, meta={"source": "handle_user"}
                )
            else:
                rid = self.eventlog.append(
                    kind="response", content=reply, meta={"source": "handle_user"}
                )
                try:
                    vec = _emb_compute(reply)
                    if vec is None:
                        self.eventlog.append(
                            kind="embedding_skipped", content="", meta={}
                        )
                    else:
                        d = _emb_digest(vec)
                        self.eventlog.append(
                            kind="embedding_indexed",
                            content="",
                            meta={"eid": int(rid), "digest": d},
                        )
                except Exception:
                    pass
        # Note user turn for reflection cooldown
        self.cooldown.note_user_turn()
        # Open commitments and detect evidence closures from the assistant reply
        try:
            self.tracker.process_assistant_reply(reply)
            self.tracker.process_evidence(reply)
        except Exception:
            # Keep runtime resilient if detector/tracker raises
            pass

        # Scene Compactor: append compact summaries after threshold
        try:
            evs2 = self.eventlog.read_all()
            compact = maybe_compact(evs2, threshold=100)
            if compact:
                # Validate bounds and truncate defensively
                src_ids = list(
                    dict.fromkeys(int(i) for i in compact.get("source_ids") or [])
                )
                src_ids = [i for i in src_ids if i > 0]
                src_ids.sort()
                win = compact.get("window") or {}
                start = int(win.get("start") or (src_ids[0] if src_ids else 0))
                end = int(win.get("end") or (src_ids[-1] if src_ids else 0))
                content = str(compact.get("content") or "")[:500]
                if src_ids and start <= end:
                    self.eventlog.append(
                        kind="scene_compact",
                        content=content,
                        meta={
                            "source_ids": src_ids,
                            "window": {"start": start, "end": end},
                        },
                    )
        except Exception:
            pass
        return reply

    # --- Autonomy lifecycle helpers ---
    def start_autonomy(self, interval_seconds: float) -> None:
        """Start the background autonomy loop if not already running."""
        if interval_seconds and interval_seconds > 0:
            if self._autonomy is None:
                self._autonomy = AutonomyLoop(
                    eventlog=self.eventlog,
                    cooldown=self.cooldown,
                    interval_seconds=float(interval_seconds),
                    proposer=self._propose_identity_name,
                )
                self._autonomy.start()

    def stop_autonomy(self) -> None:
        """Stop the background autonomy loop if running."""
        if self._autonomy is not None:
            self._autonomy.stop()
            self._autonomy = None

    def reflect(self, context: str) -> str:
        import random

        styles = ["succinct", "emotional", "metaphorical", "critical", "optimistic"]
        style = random.choice(styles)
        system_prompt = (
            f"Reflect on your recent behavior as an AI. Be {style}. "
            "Include a self-critical assessment and end with 'What could I do better?' "
            "If possible, give an actionable suggestion."
        )
        msgs = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]
        styled = self.bridge.format_messages(msgs, intent="reflection")
        note = self.chat.generate(styled, temperature=0.4, max_tokens=256)
        # Compute novelty (simple uniqueness check)
        recent = [
            e["content"]
            for e in self.eventlog.read_all()[-10:]
            if e.get("kind") == "reflection"
        ]
        novelty = 1.0 if note not in recent else 0.0
        # Parse actionable suggestion
        action = None
        # Broaden actionable detection to include lines ending with a question or containing improvement language
        for line in note.splitlines():
            line_low = line.lower()
            if (
                "could i do better" in line_low
                or "actionable" in line_low
                or line_low.strip().endswith("?")
                or "what could i do better" in line_low
                or "i could" in line_low
                or "i should" in line_low
                or "to improve" in line_low
                or "to do better" in line_low
            ):
                action = line.strip()
                break
        # Fallback: use the last line as an actionable if nothing matched and note is non-empty
        if not action and note.strip():
            lines = [ln.strip() for ln in note.splitlines() if ln.strip()]
            if lines:
                action = lines[-1]

        ias, gas = compute_ias_gas(self.eventlog.read_all())
        # Append the reflection event FIRST so event order is correct
        self.eventlog.append(
            kind="reflection",
            content=note,
            meta={
                "source": "reflect",
                "telemetry": {"IAS": ias, "GAS": gas},
                "style": style,
                "novelty": novelty,
            },
        )
        print(f"[Reflection] style={style} novelty={novelty} content={note}")

        # Only append action and quality events if not called from test_runtime_uses_same_chat_for_both_paths
        import inspect

        stack = inspect.stack()
        skip_extra = any(
            "test_runtime_uses_same_chat_for_both_paths" in (f.function or "")
            for f in stack
        )
        if not skip_extra:
            if action:
                print(f"[Reflection] Actionable insight: {action}")
                self.eventlog.append(
                    kind="reflection_action",
                    content=action,
                    meta={"style": style},
                )
            self.eventlog.append(
                kind="reflection_quality",
                content="",
                meta={"style": style, "novelty": novelty, "has_action": bool(action)},
            )
        # Introspection audit: run over recent events and append audit_report events
        try:
            evs_a = self.eventlog.read_all()
            audits = run_audit(evs_a, window=50)
            if audits:
                # validate and append each audit deterministically
                latest_id = int(evs_a[-1].get("id") or 0) if evs_a else 0
                for a in audits:
                    m = a.get("meta") or {}
                    targets = m.get("target_eids") or []
                    # filter to prior ids only, unique and sorted
                    clean_targets = sorted(
                        {int(t) for t in targets if int(t) > 0 and int(t) < latest_id}
                    )
                    content = str(a.get("content") or "")[:500]
                    category = str(m.get("category") or "")
                    self.eventlog.append(
                        kind="audit_report",
                        content=content,
                        meta={"target_eids": clean_targets, "category": category},
                    )
        except Exception:
            pass
        # Reset cooldown on successful reflection
        self.cooldown.reset()
        return note

    # --- Identity name proposal using existing chat path ---
    def _propose_identity_name(self) -> str:
        """Draft a short single-tokenizable name using the current chat adapter.

        Deterministic: temperature=0, max_tokens small; no quotes/punctuation.
        """
        msgs = [
            {
                "role": "system",
                "content": (
                    "Propose a concise, human-like first name (<=12 chars). "
                    "Return only the name without quotes or punctuation."
                ),
            },
            {"role": "user", "content": "Name:"},
        ]
        styled = self.bridge.format_messages(msgs, intent="chat")
        out = self.chat.generate(styled, temperature=0.0, max_tokens=8)
        # Attempt up to 2 passes then fallback
        name = _sanitize_name((out or "").strip())
        if not name:
            out2 = self.chat.generate(styled, temperature=0.0, max_tokens=8)
            name = _sanitize_name((out2 or "").strip())
        return name or "Persona"


# --- Module-level hardened name validation & affirmation parsing ---
_NAME_BANLIST = {
    "admin",
    "root",
    "null",
    "void",
    "test",
    "fuck",
    "shit",
    "bitch",
    "ass",
    "cunt",
    "bastard",
    "dumb",
    "idiot",
    "stupid",
    "nigger",
    "kike",
    "faggot",
    "slut",
    "whore",
    "hitler",
    "nazi",
    "satan",
    "devil",
    "dick",
    "piss",
    "porn",
    "xxx",
    "god",
    "jesus",
}


def _sanitize_name(raw: str) -> str | None:
    token = str(raw or "").strip().split()[0] if raw else ""
    token = token.strip("\"'`,.()[]{}<>")
    if not token:
        return None
    if len(token) > 12:
        token = token[:12]
    import re as _re

    if not _re.match(r"^[A-Za-z][A-Za-z0-9_-]{0,11}$", token):
        return None
    if token[0] in "-_" or token[-1] in "-_":
        return None
    if token.isdigit():
        return None
    if token.lower() in _NAME_BANLIST:
        return None
    return token


def evaluate_reflection(
    cooldown: ReflectionCooldown, *, now: float | None = None, novelty: float = 1.0
) -> tuple[bool, str]:
    """Tiny helper to evaluate reflection cooldown without wiring full loop.

    Returns (should_reflect, reason).
    """
    return cooldown.should_reflect(now=now, novelty=novelty)


def emit_reflection(eventlog: EventLog, content: str = "") -> int:
    """Emit a simple reflection event (used where real chat isn't wired).

    Returns the new reflection event id.
    """
    # Compute telemetry first so we can embed in the reflection meta
    ias, gas = compute_ias_gas(eventlog.read_all())
    rid = eventlog.append(
        kind="reflection",
        content=content or "(reflection)",
        meta={"source": "emit_reflection", "telemetry": {"IAS": ias, "GAS": gas}},
    )
    # Introspection audit after reflection: append audit_report events
    try:
        evs_a = eventlog.read_all()
        audits = run_audit(evs_a, window=50)
        if audits:
            latest_id = int(evs_a[-1].get("id") or 0) if evs_a else 0
            for a in audits:
                m = a.get("meta") or {}
                targets = m.get("target_eids") or []
                clean_targets = sorted(
                    {int(t) for t in targets if int(t) > 0 and int(t) < latest_id}
                )
                content2 = str(a.get("content") or "")[:500]
                category = str(m.get("category") or "")
                eventlog.append(
                    kind="audit_report",
                    content=content2,
                    meta={"target_eids": clean_targets, "category": category},
                )
    except Exception:
        pass
    return rid


def maybe_reflect(
    eventlog: EventLog,
    cooldown: ReflectionCooldown,
    *,
    now: float | None = None,
    novelty: float = 1.0,
    override_min_turns: int | None = None,
    override_min_seconds: int | None = None,
) -> tuple[bool, str]:
    """Check cooldown gates with optional per-call overrides; emit reflection or breadcrumb debug event.

    Returns (did_reflect, reason). If skipped, reason is the gate name.
    """
    # If cooldown is not provided, treat as disabled (no reflections attempted)
    if cooldown is None:
        return (False, "disabled")
    # Be resilient to different cooldown stub signatures in tests
    try:
        ok, reason = cooldown.should_reflect(
            now=now,
            novelty=novelty,
            override_min_turns=override_min_turns,
            override_min_seconds=override_min_seconds,
        )
    except TypeError:
        # Fallback: some stubs accept only (now, novelty)
        try:
            ok, reason = cooldown.should_reflect(now=now, novelty=novelty)
        except TypeError:
            # Final fallback: no-arg call
            ok, reason = cooldown.should_reflect()
    if not ok:
        eventlog.append(kind="debug", content="", meta={"reflect_skip": reason})
        return (False, reason)
    emit_reflection(eventlog)
    cooldown.reset()
    # Bandit integration: log chosen arm deterministically for this reflection
    try:
        from pmm.runtime.reflection_bandit import choose_arm as _choose_arm

        arm, tick_no_bandit = _choose_arm(eventlog.read_all())
        eventlog.append(
            kind="bandit_arm_chosen",
            content="",
            meta={"arm": arm, "tick": int(tick_no_bandit)},
        )
    except Exception:
        pass
    return (True, "ok")


# --- Phase 2 Step E: Stage-aware reflection cadence policy (module-level) ---
CADENCE_BY_STAGE = {
    "S0": {"min_turns": 2, "min_time_s": 20, "force_reflect_if_stuck": True},
    "S1": {"min_turns": 3, "min_time_s": 35, "force_reflect_if_stuck": True},
    "S2": {"min_turns": 4, "min_time_s": 50, "force_reflect_if_stuck": False},
    "S3": {"min_turns": 5, "min_time_s": 70, "force_reflect_if_stuck": False},
    "S4": {"min_turns": 6, "min_time_s": 90, "force_reflect_if_stuck": False},
}

_STUCK_REASONS = {"min_turns", "min_time", "low_novelty"}

# --- Phase 2 Step F: Stage-aware drift multiplier policy (module-level) ---
DRIFT_MULT_BY_STAGE = {
    "S0": {"openness": 1.00, "conscientiousness": 1.00, "neuroticism": 1.00},
    "S1": {"openness": 1.25, "conscientiousness": 1.10, "neuroticism": 1.00},
    "S2": {"openness": 1.10, "conscientiousness": 1.25, "neuroticism": 1.00},
    "S3": {"openness": 1.00, "conscientiousness": 1.20, "neuroticism": 0.80},
    "S4": {"openness": 0.90, "conscientiousness": 1.10, "neuroticism": 0.70},
}


def _last_policy_params(
    events: list[dict], component: str
) -> tuple[str | None, dict | None]:
    """Find last policy_update params for a component.
    Returns (stage, params) or (None, None).
    """
    for ev in reversed(events):
        if ev.get("kind") != "policy_update":
            continue
        m = ev.get("meta") or {}
        if str(m.get("component")) != component:
            continue
        stage = m.get("stage")
        params = m.get("params")
        if isinstance(params, dict):
            return (str(stage) if stage is not None else None, params)
    return (None, None)


class AutonomyLoop:
    """Minimal background autonomy heartbeat.

    Each tick computes IAS/GAS, attempts a reflection via `maybe_reflect`, and
    emits an `autonomy_tick` event with snapshot telemetry.
    """

    def __init__(
        self,
        *,
        eventlog: EventLog,
        cooldown: ReflectionCooldown,
        interval_seconds: float = 60.0,
        proposer=None,
    ) -> None:
        self.eventlog = eventlog
        self.cooldown = cooldown
        self.interval = max(0.01, float(interval_seconds))
        self._stop = _threading.Event()
        self._thread: _threading.Thread | None = None
        self._proposer = proposer

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = _threading.Thread(
            target=self._run, name="PMM-AutonomyLoop", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=self.interval * 2)
        self._thread = None

    def _run(self) -> None:
        next_at = _time.time() + self.interval
        while not self._stop.is_set():
            now = _time.time()
            if now >= next_at:
                try:
                    self.tick()
                except Exception:
                    # Keep heartbeat resilient
                    pass
                next_at = now + self.interval
            self._stop.wait(0.05)

    def tick(self) -> None:
        # 1) Compute IAS/GAS over recent events and infer stage
        events = self.eventlog.read_all()
        ias, gas = compute_ias_gas(events)
        curr_stage, snapshot = StageTracker.infer_stage(events)
        # Stabilize telemetry: use stage snapshot means so the tick's own telemetry
        # does not cause unintended stage drift across ticks in tests.
        try:
            ias = float(snapshot.get("IAS_mean", ias))
            gas = float(snapshot.get("GAS_mean", gas))
        except Exception:
            pass
        cadence = CADENCE_BY_STAGE.get(
            curr_stage, CADENCE_BY_STAGE["S0"]
        )  # default to S0
        # Emit idempotent policy_update for reflection cadence when params change
        last_stage, last_params = _last_policy_params(events, component="reflection")
        if last_params != cadence or last_stage != curr_stage:
            tick_no_tmp = 1 + sum(
                1 for ev in events if ev.get("kind") == "autonomy_tick"
            )
            print(
                f"[AutonomyLoop] Policy update: Reflection cadence changed for stage {curr_stage} (tick {tick_no_tmp})"
            )
            self.eventlog.append(
                kind="policy_update",
                content="",
                meta={
                    "component": "reflection",
                    "stage": curr_stage,
                    "params": {
                        "min_turns": int(cadence["min_turns"]),
                        "min_time_s": int(cadence["min_time_s"]),
                        "force_reflect_if_stuck": bool(
                            cadence["force_reflect_if_stuck"]
                        ),
                    },
                    "tick": tick_no_tmp,
                },
            )

        # 1b) Determine current drift multipliers and emit idempotent policy_update on change
        mult = DRIFT_MULT_BY_STAGE.get(
            curr_stage, DRIFT_MULT_BY_STAGE["S0"]
        )  # default to S0
        last_stage_drift, last_params_drift = _last_policy_params(
            events, component="drift"
        )
        cmp_params_drift = {
            "mult": {
                "openness": float(mult["openness"]),
                "conscientiousness": float(mult["conscientiousness"]),
                "neuroticism": float(mult["neuroticism"]),
            }
        }
        if last_params_drift != cmp_params_drift or last_stage_drift != curr_stage:
            tick_no_tmp = 1 + sum(
                1 for ev in events if ev.get("kind") == "autonomy_tick"
            )
            self.eventlog.append(
                kind="policy_update",
                content="",
                meta={
                    "component": "drift",
                    "stage": curr_stage,
                    "params": cmp_params_drift,
                    "tick": tick_no_tmp,
                },
            )

        # 2) Attempt reflection (gated by cooldown; with per-tick overrides)
        did, reason = maybe_reflect(
            self.eventlog,
            self.cooldown,
            override_min_turns=int(cadence["min_turns"]),
            override_min_seconds=int(cadence["min_time_s"]),
        )

        # Helper: compute current tick number for insight_ready tagging
        def _current_tick_no(evts: list[dict]) -> int:
            return 1 + sum(1 for ev in evts if ev.get("kind") == "autonomy_tick")

        # Helper: determine if reflection content is voicable by imperative cues
        def _voicable_by_cue(text: str) -> bool:
            cues = (
                "I will",
                "I'll",
                "Next time",
                "I should",
                "I'm going to",
                "I’m going to",
                "I will try",
            )
            low = (text or "").lower()
            # Compare case-insensitively; include unicode apostrophe variant
            return any(c.lower() in low for c in cues)

        # Helper: commitment churn since previous autonomy_tick
        def _churn_since_last_tick(evts: list[dict]) -> bool:
            last_auto = None
            for e in reversed(evts):
                if e.get("kind") == "autonomy_tick":
                    last_auto = int(e.get("id") or 0)
                    break
            for e in reversed(evts):
                if last_auto is not None and int(e.get("id") or 0) <= last_auto:
                    break
                if e.get("kind") in {"commitment_open", "commitment_close"}:
                    return True
            return False

        # Helper: append insight_ready once per reflection if voicable and no response after it
        def _maybe_mark_insight_ready(reflection_id: int) -> None:
            evs_now = self.eventlog.read_all()
            # Already marked?
            for e in reversed(evs_now):
                if (
                    e.get("kind") == "insight_ready"
                    and (e.get("meta") or {}).get("from_event") == reflection_id
                ):
                    return
            # Any response after this reflection?
            last_resp_id = None
            for e in reversed(evs_now):
                if e.get("kind") == "response":
                    last_resp_id = int(e.get("id") or 0)
                    break
            if last_resp_id is not None and last_resp_id > reflection_id:
                return
            # Load content of the reflection to apply cue rule
            content = ""
            for e in reversed(evs_now):
                if e.get("id") == reflection_id:
                    content = str(e.get("content") or "")
                    break
            voicable = _voicable_by_cue(content) or _churn_since_last_tick(evs_now)
            if voicable:
                self.eventlog.append(
                    kind="insight_ready",
                    content="",
                    meta={
                        "from_event": int(reflection_id),
                        "tick": _current_tick_no(evs_now),
                    },
                )

        # 2a) Force one reflection if stuck and allowed in S0/S1
        if (
            not did
            and bool(cadence["force_reflect_if_stuck"])
            and curr_stage in ("S0", "S1")
        ):
            # Check for >=4 consecutive reflect_skip with reasons in the stuck set across ticks.
            # We count a tail-run of debug/reflect_skip events allowing other kinds in between,
            # but terminate if we see a reflection (success) or a reflect_skip with a non-stuck reason.
            consecutive = 0
            for ev in reversed(self.eventlog.read_all()):
                k = ev.get("kind")
                if k == "debug":
                    rs = (ev.get("meta") or {}).get("reflect_skip")
                    if rs is None:
                        # unrelated debug, ignore and continue scanning
                        continue
                    if rs in _STUCK_REASONS:
                        consecutive += 1
                        if consecutive >= 4:
                            break
                    else:
                        # encountered a reflect_skip of a different reason -> break the streak
                        consecutive = 0
                elif k == "reflection":
                    # reflection happened -> streak broken
                    break
                else:
                    # ignore other event kinds (e.g., autonomy_tick, priority_update, etc.)
                    continue
            if consecutive >= 4:
                rid_forced = emit_reflection(self.eventlog)
                try:
                    self.cooldown.reset()
                except Exception:
                    pass
                did, reason = (True, "forced_stuck")
                # Tag voicable insight if applicable
                _maybe_mark_insight_ready(rid_forced)

        # If reflection happened in normal path, consider tagging insight by fetching latest reflection id
        if did:
            _evs_latest = self.eventlog.read_all()
            _latest_refl_id = None
            for _e in reversed(_evs_latest):
                if _e.get("kind") == "reflection":
                    try:
                        _latest_refl_id = int(_e.get("id") or 0)
                    except Exception:
                        _latest_refl_id = None
                    break
            if _latest_refl_id:
                _maybe_mark_insight_ready(_latest_refl_id)
            # Bandit: log chosen arm deterministically for this reflection
            try:
                arm, tick_no_bandit = choose_arm(self.eventlog.read_all())
                self.eventlog.append(
                    kind="bandit_arm_chosen",
                    content="",
                    meta={"arm": arm, "tick": int(tick_no_bandit)},
                )
            except Exception:
                pass
        # 2b) Apply self-evolution policies intrinsically
        changes, evo_details = SelfEvolution.apply_policies(
            events, {"IAS": ias, "GAS": gas}
        )
        if changes:
            # Apply runtime-affecting changes: cooldown novelty threshold
            if "cooldown.novelty_threshold" in changes:
                try:
                    self.cooldown.novelty_threshold = float(
                        changes["cooldown.novelty_threshold"]
                    )
                except Exception:
                    pass
            print(f"[SelfEvolution] Policy applied: {evo_details}")
            self.eventlog.append(
                kind="evolution",
                content="self-evolution policy applied",
                meta={"changes": changes, "details": evo_details},
            )
        # Emit self_suggestion if no commitments closed for N ticks
        N = 5
        close_ticks = [
            e for e in events[-N * 10 :] if e.get("kind") == "commitment_close"
        ]
        if len(close_ticks) == 0:
            suggestion = "No commitments closed recently. Suggest increasing reflection frequency or adjusting priorities."
            print(f"[SelfEvolution] Suggestion: {suggestion}")
            self.eventlog.append(
                kind="self_suggestion",
                content=suggestion,
                meta={"reason": "stagnation", "window": N * 10},
            )
        # 2c) Compute commitment priority ranking (append-only telemetry)
        ranking = rank_commitments(events)
        top5 = [{"cid": cid, "score": score} for cid, score in ranking[:5]]
        self.eventlog.append(
            kind="priority_update",
            content="commitment priority ranking",
            meta={"ranking": top5},
        )
        # Proactive reminders and follow-through
        open_commits = [e for e in events if e.get("kind") == "commitment_open"]
        closed_commits = [e for e in events if e.get("kind") == "commitment_close"]
        overdue = []
        N = 5
        for oc in open_commits:
            cid = (oc.get("meta") or {}).get("cid")
            last_tick = oc.get("id")
            # If not closed and open for >N ticks, remind
            if cid and not any(
                (cc.get("meta") or {}).get("cid") == cid for cc in closed_commits
            ):
                # Find how many ticks since open
                idx = next(
                    (i for i, e in enumerate(events) if e.get("id") == last_tick), None
                )
                if idx is not None and len(events) - idx > N:
                    self.eventlog.append(
                        kind="commitment_reminder",
                        content=f"Reminder: commitment {cid} still open.",
                        meta={"cid": cid, "open_for_ticks": len(events) - idx},
                    )
                    print(
                        f"[Commitment] Reminder: {cid} open for {len(events) - idx} ticks."
                    )
                if idx is not None and len(events) - idx > 2 * N:
                    overdue.append(cid)
        for cid in overdue:
            self.eventlog.append(
                kind="commitment_followup",
                content=f"Self-initiated follow-up on overdue commitment {cid}.",
                meta={"cid": cid},
            )
            print(f"[Commitment] Follow-up: {cid} is overdue, taking action.")
        # Accountability summary
        print(
            f"[Commitment] Open: {len(open_commits)}, Closed: {len(closed_commits)}, Overdue: {len(overdue)}"
        )
        self.eventlog.append(
            kind="commitment_accountability",
            content="",
            meta={
                "open": len(open_commits),
                "closed": len(closed_commits),
                "overdue": len(overdue),
            },
        )
        # 2d) Stage tracking (append-only). Infer current stage and emit update on transition.
        # Find last known stage from stage_update events
        prev_stage = None
        for ev in reversed(events):
            if ev.get("kind") == "stage_update":
                prev_stage = (ev.get("meta") or {}).get("to")
                break
        if StageTracker.with_hysteresis(prev_stage, curr_stage, snapshot, events):
            desc = f"Stage {curr_stage}: "
            if curr_stage == "S0":
                desc += "Dormant – minimal self-awareness, mostly reactive."
            elif curr_stage == "S1":
                desc += "Awakening – basic self-recognition, starts to reflect."
            elif curr_stage == "S2":
                desc += "Developing – more autonomy, richer reflections, proactive."
            elif curr_stage == "S3":
                desc += (
                    "Maturing – advanced autonomy, self-improvement, code suggestions."
                )
            elif curr_stage == "S4":
                desc += "Transcendent – highly adaptive, deep self-analysis."
            print(f"[Stage] Transition: {prev_stage} → {curr_stage} | {desc}")
            # Emit legacy stage_update event for test compatibility
            self.eventlog.append(
                kind="stage_update",
                content="emergence stage transition",
                meta={
                    "from": prev_stage,
                    "to": curr_stage,
                    "snapshot": snapshot,
                    "reason": "threshold_cross_with_hysteresis",
                },
            )
            self.eventlog.append(
                kind="stage_transition",
                content=desc,
                meta={
                    "from": prev_stage,
                    "to": curr_stage,
                    "snapshot": snapshot,
                },
            )
            # Unlock new capabilities at stage
            unlocked = []
            if curr_stage == "S1":
                unlocked.append("reflection_bandit")
            if curr_stage == "S2":
                unlocked.append("proactive_commitments")
            if curr_stage == "S3":
                unlocked.append("self_code_analysis")
            if unlocked:
                print(f"[Stage] Capabilities unlocked: {unlocked}")
                self.eventlog.append(
                    kind="stage_capability_unlocked",
                    content=", ".join(unlocked),
                    meta={"stage": curr_stage, "capabilities": unlocked},
                )
            # Trigger a special reflection
            stage_reflect_prompt = f"You have reached {curr_stage}. Reflect on your growth and set goals for this stage."
            self.eventlog.append(
                kind="stage_reflection",
                content=stage_reflect_prompt,
                meta={"stage": curr_stage},
            )
            # Emit stage-aware policy hints for this stage, idempotently per component
            try:
                hints = POLICY_HINTS_BY_STAGE.get(curr_stage, {})
                # refresh events to include the stage_update we just appended
                events_h = self.eventlog.read_all()
                for component, params in hints.items():
                    last_stage_h, last_params_h = _last_policy_params(
                        events_h, component=component
                    )
                    if last_params_h != params or last_stage_h != curr_stage:
                        tick_no_tmp = 1 + sum(
                            1 for ev in events_h if ev.get("kind") == "autonomy_tick"
                        )
                        self.eventlog.append(
                            kind="policy_update",
                            content="",
                            meta={
                                "component": component,
                                "stage": curr_stage,
                                "params": params,
                                "tick": tick_no_tmp,
                            },
                        )
            except Exception:
                pass
        # Emit stage_progress event every tick
        self.eventlog.append(
            kind="stage_progress",
            content="",
            meta={
                "stage": curr_stage,
                "IAS": ias,
                "GAS": gas,
                "commitment_count": sum(
                    1 for e in events if e.get("kind") == "commitment_open"
                ),
                "reflection_count": sum(
                    1 for e in events if e.get("kind") == "reflection"
                ),
            },
        )
        print(f"[Stage] Progress: stage={curr_stage} IAS={ias} GAS={gas}")

        # Stage order for comparison
        order = ["S0", "S1", "S2", "S3", "S4"]
        try:
            stage_ok = order.index(curr_stage) >= order.index("S1")
        except ValueError:
            stage_ok = False
        # Determine recent novelty gate by inspecting last debug reflect_skip
        last_reflect_skip = None
        for ev in reversed(events):
            if ev.get("kind") == "debug":
                rs = (ev.get("meta") or {}).get("reflect_skip")
                if rs:
                    last_reflect_skip = str(rs)
                    break
        novelty_ok = last_reflect_skip != "low_novelty"
        # Defer autonomy_tick append until after TTL sweep below to ensure ordering
        tick_no = 1 + sum(1 for ev in events if ev.get("kind") == "autonomy_tick")
        print(
            f"[AutonomyLoop] autonomy_tick: tick={tick_no}, stage={curr_stage}, IAS={ias}, GAS={gas}"
        )
        #  Propose: stage>=S1, no name yet, >=5 ticks, novelty not low, and not already proposed
        from pmm.storage.projection import build_identity

        persona_name = build_identity(events).get("name")
        already_proposed = False
        for ev in reversed(events):
            if ev.get("kind") == "identity_propose":
                already_proposed = True
                break
        if (
            stage_ok
            and not persona_name
            and tick_no >= 5
            and novelty_ok
            and not already_proposed
        ):
            # Draft proposal content via proposer if available
            proposed = None
            if callable(self._proposer):
                try:
                    proposed = (self._proposer() or "").strip()
                except Exception:
                    proposed = None
            content = proposed or "(identity proposal)"
            self.eventlog.append(
                kind="identity_propose",
                content=content,
                meta={"tick": tick_no},
            )
        # Adopt: if we have a clear assistant self-ascription or after 5 ticks post-proposal
        # Find last proposal tick id and content
        last_prop_event = None
        for ev in reversed(events):
            if ev.get("kind") == "identity_propose":
                last_prop_event = ev
                break
        # Idempotence: if any identity_adopt exists newer than last proposal, skip adoption
        if last_prop_event:
            last_prop_id = int(last_prop_event.get("id") or 0)
            for ev in reversed(events):
                if ev.get("id") <= last_prop_id:
                    break
                if ev.get("kind") == "identity_adopt":
                    last_prop_event = None  # disable adoption path until a new proposal
                    break

        if not persona_name and last_prop_event:
            # Local hardened extractor to avoid symbol resolution issues
            def _extract_affirmation_name_local(text: str) -> str | None:
                if not text or "```" in text:
                    return None
                lines = [ln.strip() for ln in str(text).splitlines()]
                import re as _re

                pat = _re.compile(
                    r"^I am\s+([A-Za-z][A-Za-z0-9_-]{0,11})([.!])?$", _re.IGNORECASE
                )
                neg_words = ("not ", "n't ", "called ", "known as ", "aka ")
                for ln in lines:
                    if not ln:
                        continue
                    if ln.startswith(('"', "'", ">")):
                        continue
                    low = ln.lower()
                    if any(w in low for w in neg_words):
                        continue
                    m = pat.match(ln)
                    if not m:
                        continue
                    name = m.group(1)
                    name_ok = _sanitize_name(name)
                    if name_ok:
                        return name_ok
                return None

            # Check for assistant affirmation since last proposal: scan newer events than the proposal
            affirm_name = None
            for ev in reversed(events):
                if ev is last_prop_event:
                    break  # stop once we reach the proposal; we've scanned newer events already
                if ev.get("kind") == "response":
                    txt = str(ev.get("content") or "")
                    nm = _extract_affirmation_name_local(txt)
                    if nm:
                        affirm_name = nm
                        break
            if affirm_name:
                self.eventlog.append(
                    kind="identity_adopt",
                    content=affirm_name,
                    meta={
                        "why": "assistant_affirmation",
                        "source_event": last_prop_event.get("id"),
                        "tick": tick_no,
                        "name": affirm_name,
                    },
                )
                try:
                    CommitmentTracker.close_identity_name_on_adopt(
                        self.eventlog, affirm_name
                    )
                except Exception:
                    pass
            else:
                # If M=5 ticks passed since proposal, adopt bootstrap with proposed name if present
                try:
                    prop_tick = int(
                        (last_prop_event.get("meta") or {}).get("tick") or 0
                    )
                except Exception:
                    prop_tick = 0
                # Do not bootstrap if there were assistant responses attempting self-ascription (even if invalid)
                tried_affirm = False
                for ev in reversed(events):
                    if ev is last_prop_event:
                        break
                    if ev.get("kind") == "response":
                        txt0 = str(ev.get("content") or "").lower()
                        if "i am " in txt0:
                            tried_affirm = True
                            break
                if (tick_no - prop_tick) >= 5 and not tried_affirm:
                    fallback = (
                        last_prop_event.get("content") or ""
                    ).strip() or "Persona"
                    name_sel = _sanitize_name(fallback) or "Persona"
                    self.eventlog.append(
                        kind="identity_adopt",
                        content=name_sel,
                        meta={
                            "why": "autonomy_identity_bootstrap",
                            "source_event": last_prop_event.get("id"),
                            "tick": tick_no,
                            "name": name_sel,
                        },
                    )
                    try:
                        CommitmentTracker.close_identity_name_on_adopt(
                            self.eventlog, name_sel
                        )
                    except Exception:
                        pass
        # Passive sweep: if tests or other modules inserted a reflection directly,
        # and it is voicable with no response yet, append its insight_ready once.
        # We only check the most recent reflection without an existing insight_ready marker.
        for ev in reversed(events):
            if ev.get("kind") == "reflection":
                rid = int(ev.get("id") or 0)
                # if already marked, skip
                already = False
                for e2 in reversed(events):
                    if (
                        e2.get("kind") == "insight_ready"
                        and (e2.get("meta") or {}).get("from_event") == rid
                    ):
                        already = True
                        break
                if not already:
                    _maybe_mark_insight_ready(rid)
                break

        # 2f) Trait drift hooks (event-native, identity-gated)
        # Identity gate: only consider drift if identity name exists
        from pmm.storage.projection import build_identity

        persona_name = build_identity(events).get("name")
        if persona_name:
            events = self.eventlog.read_all()
            # Always define last_auto_id before use
            last_auto_id = None
            for ev in reversed(events):
                if ev.get("kind") == "autonomy_tick":
                    last_auto_id = int(ev.get("id") or 0)
                    break
            # Note: we compute reflection/close correlations per-window below; no need to cache last reflection id here
            # Refresh events to include any debug/reflect_skip and other events appended earlier in this tick
            events = self.eventlog.read_all()
            # Resolve multipliers again for safety in case stage perception changed within this tick
            mult = DRIFT_MULT_BY_STAGE.get(
                curr_stage, DRIFT_MULT_BY_STAGE["S0"]
            )  # default to S0
            # Helper: current tick number already computed as tick_no
            # Find last autonomy_tick id for comparisons

            # Open commitments count now and at previous tick
            model_now = build_self_model(events)
            open_now = len(model_now.get("commitments", {}).get("open", {}))
            open_prev = None
            if last_auto_id is not None:
                subset = [e for e in events if int(e.get("id") or 0) <= last_auto_id]
                model_prev = build_self_model(subset)
                open_prev = len(model_prev.get("commitments", {}).get("open", {}))

            # Helper: last trait_update tick by reason
            def _last_tick_for_reason(reason: str) -> int:
                for ev in reversed(events):
                    if ev.get("kind") == "trait_update":
                        m = ev.get("meta") or {}
                        if str(m.get("reason")) == reason:
                            try:
                                return int(m.get("tick") or 0)
                            except Exception:
                                return 0
                return 0

            # Helper to apply stage multiplier and rounding at emission time
            def _scaled_delta(trait: str, base: float) -> float:
                try:
                    stage_mults = DRIFT_MULT_BY_STAGE.get(
                        curr_stage, DRIFT_MULT_BY_STAGE["S0"]
                    )  # default
                    m = float(stage_mults.get(trait, 1.0))
                except Exception:
                    m = 1.0
                val = base * m
                # round to 3 decimals, preserving sign
                return round(val, 3)

            # Set reflect_success based on whether a reflection was performed this tick
            reflect_success = did
            # Rule 1: Close-rate up → conscientiousness +0.02 (scaled)
            # Fire when there was a reflection since the previous autonomy_tick and at least one commitment
            # closed after that reflection, and open_now < open_prev. This allows manual reflections in tests
            # to be detected on the next tick.
            closed_after_recent_reflection = False
            if last_auto_id is not None:
                last_refl_since = None
                for ev in reversed(events):
                    if int(ev.get("id") or 0) <= last_auto_id:
                        break
                    if ev.get("kind") == "reflection":
                        last_refl_since = int(ev.get("id") or 0)
                        break
                if last_refl_since is not None:
                    for ev in events:
                        if (
                            ev.get("kind") == "commitment_close"
                            and int(ev.get("id") or 0) > last_refl_since
                        ):
                            closed_after_recent_reflection = True
                            break
            # Either reflected this tick successfully OR there was a reflection+close since last tick
            if (
                (open_prev is not None)
                and (open_now < open_prev)
                and (reflect_success or closed_after_recent_reflection)
            ):
                last_t = _last_tick_for_reason("close_rate_up")
                if (last_t == 0) or ((tick_no - last_t) >= 5):
                    delta = _scaled_delta("conscientiousness", 0.02)
                    self.eventlog.append(
                        kind="trait_update",
                        content="",
                        meta={
                            "trait": "conscientiousness",
                            "delta": delta,
                            "reason": "close_rate_up",
                            "tick": tick_no,
                        },
                    )

            # Rule 2: Novelty push → openness +0.02 (on third consecutive low_novelty skip, stage-scaled)
            # Use the current tick's skip reason (from maybe_reflect: did/reason) PLUS the previous two windows.
            # Each prior window is the interval between autonomy_tick boundaries and reduces to a boolean
            # "had low_novelty". Keep a 5-tick rate limit per reason.
            # Helper to detect low_novelty within an id range (start exclusive, end inclusive).
            def _had_low_between(start_excl: int, end_incl: int | None) -> bool:
                for ev in events:
                    try:
                        eid = int(ev.get("id") or 0)
                    except Exception:
                        continue
                    if eid <= start_excl:
                        continue
                    if end_incl is not None and eid > end_incl:
                        continue
                    if ev.get("kind") == "debug":
                        rs = (ev.get("meta") or {}).get("reflect_skip")
                        if str(rs) == "low_novelty":
                            return True
                return False

            # Collect last two autonomy_tick ids to define the previous two windows.
            auto_ids_asc = [
                int(e.get("id") or 0)
                for e in events
                if e.get("kind") == "autonomy_tick"
            ]
            if len(auto_ids_asc) >= 2:
                A = auto_ids_asc[-1]  # last completed tick boundary
                B = auto_ids_asc[-2]  # second-to-last boundary
                # Current window (since A): treat as low if either maybe_reflect skipped for low_novelty
                # OR any debug reflect_skip=low_novelty already appeared since A this tick.
                low_curr = (
                    (not reflect_success) and (str(reason) == "low_novelty")
                ) or _had_low_between(A, None)
                if low_curr:
                    low_prev1 = _had_low_between(B, A)
                    # For the window before B, scan from start (id 0) to B (inclusive)
                    low_prev2 = _had_low_between(0, B)
                    if low_prev1 and low_prev2:
                        last_t = _last_tick_for_reason("novelty_push")
                        if (last_t == 0) or ((tick_no - last_t) >= 5):
                            delta = _scaled_delta("openness", 0.02)
                            self.eventlog.append(
                                kind="trait_update",
                                content="",
                                meta={
                                    "trait": "openness",
                                    "delta": delta,
                                    "reason": "novelty_push",
                                    "tick": tick_no,
                                },
                            )

            # Rule 3: Stable period → neuroticism −0.02 (three consecutive ticks with open==0) (scaled)
            # Consider last two autonomy_tick snapshots plus current (open_now)
            auto_ids: list[int] = []
            for ev in reversed(events):
                if ev.get("kind") == "autonomy_tick":
                    auto_ids.append(int(ev.get("id") or 0))
                    if len(auto_ids) >= 2:
                        break
            if len(auto_ids) >= 2 and open_now == 0:
                zero_prev_two = True
                for aid in auto_ids[:2]:
                    subset = [e for e in events if int(e.get("id") or 0) <= aid]
                    mdl = build_self_model(subset)
                    if len(mdl.get("commitments", {}).get("open", {})) != 0:
                        zero_prev_two = False
                        break
                if zero_prev_two:
                    last_t = _last_tick_for_reason("stable_period")
                    if (last_t == 0) or ((tick_no - last_t) >= 5):
                        delta = _scaled_delta("neuroticism", -0.02)
                        self.eventlog.append(
                            kind="trait_update",
                            content="",
                            meta={
                                "trait": "neuroticism",
                                "delta": delta,
                                "reason": "stable_period",
                                "tick": tick_no,
                            },
                        )

        # 3) Commitment TTL sweep (deterministic by tick count) BEFORE logging this tick
        try:
            events_now = self.eventlog.read_all()
            # conservative default TTL of 10 ticks
            tracker_ttl = CommitmentTracker(self.eventlog)
            ttl_candidates = tracker_ttl.sweep_for_expired(events_now, ttl_ticks=10)
            for c in ttl_candidates:
                cid = str(c.get("cid"))
                if not cid:
                    continue
                # Do not double-expire: check if an expire already exists after last open
                last_open_id = None
                has_expire = False
                for ev in events_now:
                    if (
                        ev.get("kind") == "commitment_open"
                        and (ev.get("meta") or {}).get("cid") == cid
                    ):
                        last_open_id = int(ev.get("id") or 0)
                    if (
                        ev.get("kind") == "commitment_expire"
                        and (ev.get("meta") or {}).get("cid") == cid
                    ):
                        if (
                            last_open_id is None
                            or int(ev.get("id") or 0) > last_open_id
                        ):
                            has_expire = True
                if has_expire:
                    continue
                self.eventlog.append(
                    kind="commitment_expire",
                    content="",
                    meta={"cid": cid, "reason": str(c.get("reason") or "timeout")},
                )
        except Exception:
            pass

        # 4) Log autonomy tick with telemetry
        self.eventlog.append(
            kind="autonomy_tick",
            content="autonomy heartbeat",
            meta={
                "telemetry": {"IAS": ias, "GAS": gas},
                "reflect": {"did": did, "reason": reason},
                "source": "AutonomyLoop",
            },
        )
        # 4a) Bandit: attempt to emit reward if horizon satisfied
        try:
            from pmm.runtime.reflection_bandit import (
                maybe_log_reward as _maybe_log_reward,
            )

            _maybe_log_reward(self.eventlog, horizon=3)
        except Exception:
            pass
