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
from pmm.runtime.prioritizer import rank_commitments
from pmm.runtime.stage_tracker import StageTracker
from pmm.runtime.bridge import ResponseRenderer


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
        reply = self._renderer.render(reply, ident, stage=None)
        self.eventlog.append(
            kind="response", content=reply, meta={"source": "handle_user"}
        )
        # Note user turn for reflection cooldown
        self.cooldown.note_user_turn()
        # Open commitments and detect evidence closures from the assistant reply
        try:
            self.tracker.process_assistant_reply(reply)
            self.tracker.process_evidence(reply)
        except Exception:
            # Keep runtime resilient if detector/tracker raises
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
        msgs = [
            {"role": "system", "content": "Reflect briefly on recent progress."},
            {"role": "user", "content": context},
        ]
        styled = self.bridge.format_messages(msgs, intent="reflection")
        note = self.chat.generate(styled, temperature=0.2, max_tokens=256)
        # Compute telemetry and embed into reflection meta
        ias, gas = compute_ias_gas(self.eventlog.read_all())
        self.eventlog.append(
            kind="reflection",
            content=note,
            meta={"source": "reflect", "telemetry": {"IAS": ias, "GAS": gas}},
        )
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


def emit_reflection(eventlog: EventLog, content: str = "") -> None:
    """Emit a simple reflection event (used where real chat isn't wired)."""
    # Compute telemetry first so we can embed in the reflection meta
    ias, gas = compute_ias_gas(eventlog.read_all())
    eventlog.append(
        kind="reflection",
        content=content or "(reflection)",
        meta={"source": "emit_reflection", "telemetry": {"IAS": ias, "GAS": gas}},
    )


def maybe_reflect(
    eventlog: EventLog,
    cooldown: ReflectionCooldown,
    *,
    now: float | None = None,
    novelty: float = 1.0,
) -> tuple[bool, str]:
    """Check cooldown gates; emit reflection or breadcrumb debug event.

    Returns (did_reflect, reason). If skipped, reason is the gate name.
    """
    ok, reason = cooldown.should_reflect(now=now, novelty=novelty)
    if not ok:
        eventlog.append(kind="debug", content="", meta={"reflect_skip": reason})
        return (False, reason)
    emit_reflection(eventlog)
    cooldown.reset()
    return (True, "ok")


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
        # 1) Compute IAS/GAS over recent events
        events = self.eventlog.read_all()
        ias, gas = compute_ias_gas(events)
        # 2) Attempt reflection (gated by cooldown)
        did, reason = maybe_reflect(self.eventlog, self.cooldown)
        # 2b) Apply self-evolution policies intrinsically
        changes = SelfEvolution.apply_policies(events, {"IAS": ias, "GAS": gas})
        if changes:
            # Apply runtime-affecting changes: cooldown novelty threshold
            if "cooldown.novelty_threshold" in changes:
                try:
                    self.cooldown.novelty_threshold = float(
                        changes["cooldown.novelty_threshold"]
                    )
                except Exception:
                    pass
            # Log evolution event
            self.eventlog.append(
                kind="evolution",
                content="self-evolution policy applied",
                meta={"changes": changes},
            )
        # 2c) Compute commitment priority ranking (append-only telemetry)
        ranking = rank_commitments(events)
        top5 = [{"cid": cid, "score": score} for cid, score in ranking[:5]]
        self.eventlog.append(
            kind="priority_update",
            content="commitment priority ranking",
            meta={"ranking": top5},
        )
        # 2d) Stage tracking (append-only). Infer current stage and emit update on transition.
        curr_stage, snapshot = StageTracker.infer_stage(events)
        # Find last known stage from stage_update events
        prev_stage = None
        for ev in reversed(events):
            if ev.get("kind") == "stage_update":
                prev_stage = (ev.get("meta") or {}).get("to")
                break
        if StageTracker.with_hysteresis(prev_stage, curr_stage, snapshot, events):
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
        # 2e) Identity autonomy policy (intrinsic, no keywords)
        # Compute current tick number and existing identity state
        tick_no = 1 + sum(1 for ev in events if ev.get("kind") == "autonomy_tick")
        ident = build_identity(events)
        name_now = ident.get("name")
        # Determine if we already proposed
        already_proposed = any(ev.get("kind") == "identity_propose" for ev in events)
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
        #  Propose: stage>=S1, no name yet, >=5 ticks, novelty not low, and not already proposed
        if (
            stage_ok
            and not name_now
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

        if not name_now and last_prop_event:
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
        # 2f) Trait drift hooks (event-native, identity-gated)
        # Identity gate: only consider drift if identity name exists
        if name_now:
            # Helper: current tick number already computed as tick_no
            # Find last autonomy_tick id for comparisons
            last_auto_id = None
            for ev in reversed(events):
                if ev.get("kind") == "autonomy_tick":
                    last_auto_id = int(ev.get("id") or 0)
                    break

            # Compute reflect_success since previous tick
            reflect_success = False
            if last_auto_id is not None:
                for ev in reversed(events):
                    if int(ev.get("id") or 0) <= last_auto_id:
                        break
                    if ev.get("kind") == "reflection":
                        reflect_success = True
                        break
            else:
                # If no previous autonomy tick, consider no success baseline
                reflect_success = False

            # Collect last up to 10 reflect_skip reasons
            recent_skips = []
            for ev in reversed(events):
                if ev.get("kind") == "debug":
                    rs = (ev.get("meta") or {}).get("reflect_skip")
                    if rs is not None:
                        recent_skips.append(str(rs))
                        if len(recent_skips) >= 10:
                            break

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

            # Rule 1: Close-rate up → conscientiousness +0.02
            if reflect_success and (open_prev is not None) and (open_now < open_prev):
                last_t = _last_tick_for_reason("close_rate_up")
                if (last_t == 0) or ((tick_no - last_t) >= 5):
                    self.eventlog.append(
                        kind="trait_update",
                        content="",
                        meta={
                            "trait": "conscientiousness",
                            "delta": 0.02,
                            "reason": "close_rate_up",
                            "tick": tick_no,
                        },
                    )

            # Rule 2: Novelty push → openness +0.02 (three consecutive low_novelty)
            if recent_skips.count("low_novelty") >= 3:
                last_t = _last_tick_for_reason("novelty_push")
                if (last_t == 0) or ((tick_no - last_t) >= 5):
                    self.eventlog.append(
                        kind="trait_update",
                        content="",
                        meta={
                            "trait": "openness",
                            "delta": 0.02,
                            "reason": "novelty_push",
                            "tick": tick_no,
                        },
                    )

            # Rule 3: Stable period → neuroticism −0.02 (three consecutive ticks with open==0)
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
                        self.eventlog.append(
                            kind="trait_update",
                            content="",
                            meta={
                                "trait": "neuroticism",
                                "delta": -0.02,
                                "reason": "stable_period",
                                "tick": tick_no,
                            },
                        )

        # 3) Log autonomy tick with telemetry
        self.eventlog.append(
            kind="autonomy_tick",
            content="autonomy heartbeat",
            meta={
                "telemetry": {"IAS": ias, "GAS": gas},
                "reflect": {"did": did, "reason": reason},
                "source": "AutonomyLoop",
            },
        )
