"""Minimal runtime loop orchestrator for PMM v2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from pmm_v2.core.event_log import EventLog
from pmm_v2.core.ledger_mirror import LedgerMirror
from pmm_v2.core.meme_graph import MemeGraph
from pmm_v2.runtime.autonomy_kernel import AutonomyKernel, KernelDecision
from pmm_v2.runtime.commitment_manager import CommitmentManager
from pmm_v2.runtime.prompts import compose_system_prompt
from pmm_v2.runtime.reflection import TurnDelta, build_reflection_text
from pmm_v2.core.schemas import Claim
from pmm_v2.core.validators import validate_claim
from pmm_v2.core.semantic_extractor import extract_commitments, extract_claims
from pmm_v2.runtime.context_builder import build_context
from pmm_v2.runtime.reflection_synthesizer import synthesize_reflection
from pmm_v2.runtime.identity_summary import maybe_append_summary
import time


class RuntimeLoop:
    def __init__(self, *, eventlog: EventLog, adapter, replay: bool = False) -> None:
        self.eventlog = eventlog
        self.mirror = LedgerMirror(eventlog)
        self.memegraph = MemeGraph()
        # wire event listener
        self.eventlog.register_listener(self.memegraph.on_event)
        self.commitments = CommitmentManager(eventlog)
        self.adapter = adapter
        self.replay = replay
        self.autonomy = AutonomyKernel(eventlog)
        if not self.replay:
            self.autonomy.ensure_rule_table_event()

    def _extract_commitments(self, text: str) -> List[str]:
        lines = (text or "").splitlines()
        return extract_commitments(lines)

    def _extract_closures(self, text: str) -> List[str]:
        cids: List[str] = []
        for line in (text or "").splitlines():
            if line.startswith("CLOSE:"):
                cids.append(line.split(":", 1)[1].strip())
        return cids

    def _extract_claims(self, text: str) -> List[Claim]:
        lines = (text or "").splitlines()
        try:
            parsed = extract_claims(lines)
        except ValueError:
            # Keep runtime robust: skip malformed claim lines
            parsed = []
        return [Claim(type=ctype, data=data) for ctype, data in parsed]

    def _extract_reflect(self, text: str) -> Dict[str, Any] | None:
        for line in (text or "").splitlines():
            if line.startswith("REFLECT:"):
                j = line[len("REFLECT:"):]
                try:
                    return json.loads(j)
                except Exception:
                    return None
        return None

    def run_turn(self, user_input: str) -> List[Dict[str, Any]]:
        if self.replay:
            # Replay mode: do not mutate ledger; simply return existing events.
            return self.eventlog.read_all()

        # 1. Log user message
        self.eventlog.append(kind="user_message", content=user_input, meta={"role": "user"})

        # 2. Build prompts
        history = self.eventlog.read_tail(limit=10)
        open_comms = self.mirror.get_open_commitment_events()
        # Deterministic short context window
        ctx_block = build_context(self.eventlog, limit=5)
        base_prompt = compose_system_prompt(history, open_comms)
        system_prompt = f"{ctx_block}\n\n{base_prompt}" if ctx_block else base_prompt

        # 3. Invoke model
        t0 = time.perf_counter()
        assistant_reply = self.adapter.generate_reply(system_prompt=system_prompt, user_prompt=user_input)
        t1 = time.perf_counter()

        # 4. Log assistant message
        ai_event_id = self.eventlog.append(
            kind="assistant_message", content=assistant_reply, meta={"role": "assistant"}
        )
        ai_event = [e for e in self.eventlog.read_all() if e["id"] == ai_event_id][0]

        # 4b. Per-turn diagnostics (deterministic formatting)
        prov = "dummy"
        cls = type(self.adapter).__name__.lower()
        if "openai" in cls:
            prov = "openai"
        elif "ollama" in cls:
            prov = "ollama"
        model_name = getattr(self.adapter, "model", "") or ""
        in_tokens = len((system_prompt or "").split()) + len((user_input or "").split())
        out_tokens = len((assistant_reply or "").split())
        # Use adapter-provided deterministic latency if present (e.g., DummyAdapter)
        lat_ms = getattr(self.adapter, "deterministic_latency_ms", None)
        if lat_ms is None:
            lat_ms = int((t1 - t0) * 1000)
        diag = (
            f"provider:{prov},model:{model_name},"
            f"in_tokens:{in_tokens},out_tokens:{out_tokens},lat_ms:{lat_ms}"
        )
        self.eventlog.append(kind="metrics_turn", content=diag, meta={})

        # 4c. Synthesize deterministic reflection and maybe append summary
        synthesize_reflection(self.eventlog)
        maybe_append_summary(self.eventlog)

        delta = TurnDelta()

        # 5. Commitments (open)
        for c in self._extract_commitments(assistant_reply):
            cid = self.commitments.open_commitment(c, source="assistant")
            if cid:
                delta.opened.append(cid)

        # 6. Claims
        for claim in self._extract_claims(assistant_reply):
            ok, _msg = validate_claim(claim, self.eventlog, self.mirror)
            if not ok:
                delta.failed_claims.append(claim)

        # 7. Closures
        to_close = self._extract_closures(assistant_reply)
        actually_closed = self.commitments.apply_closures(to_close, source="assistant")
        delta.closed.extend(actually_closed)

        # 8. REFLECT block
        delta.reflect_block = self._extract_reflect(assistant_reply)

        # 9. Reflection append only if delta non-empty
        if not delta.is_empty():
            reflection_text = build_reflection_text(delta)
            if reflection_text:
                self.eventlog.append(
                    kind="reflection", content=reflection_text, meta={"about_event": ai_event_id}
                )

        if not self.replay:
            self.run_tick()

        return self.eventlog.read_all()

    def run_interactive(self) -> None:  # pragma: no cover - simple IO wrapper
        try:
            while True:
                inp = input("You> ")
                if inp is None:
                    break
                # Graceful exits
                if inp.strip().lower() in {"exit", ".exit", "quit"}:
                    break
                if inp.strip() == "/tick":
                    decision = self.run_tick()
                    print(f"Autonomy> {decision.decision} ({decision.reasoning})")
                    continue
                before = self.eventlog.hash_sequence()
                events = self.run_turn(inp)
                after = self.eventlog.hash_sequence()
                # Print last assistant/reflection contents
                if self.replay:
                    # In replay, nothing new; just show last assistant/reflection in log
                    for e in events[::-1]:
                        if e["kind"] in ("assistant_message", "reflection"):
                            role = "Assistant" if e["kind"] == "assistant_message" else "Reflection"
                            print(f"{role}> {e['content']}")
                            break
                else:
                    # fresh turn appended; print the last assistant
                    last_ai = [e for e in events if e["kind"] == "assistant_message"][-1]
                    # Hide COMMIT lines from user display (still logged in ledger)
                    lines = [ln for ln in (last_ai["content"] or "").splitlines() if not ln.strip().upper().startswith("COMMIT:")]
                    print(f"Assistant> {'\n'.join(lines)}")
        except (EOFError, KeyboardInterrupt):
            return

    def run_tick(self) -> KernelDecision:
        """Execute a deterministic autonomy tick."""
        if self.replay:
            return KernelDecision("idle", "replay mode (no mutations allowed)", [])

        decision = self.autonomy.decide_next_action()
        payload = json.dumps(decision.as_dict(), sort_keys=True, separators=(",", ":"))
        self.eventlog.append(
            kind="autonomy_tick",
            content=payload,
            meta={"source": "autonomy_kernel"},
        )

        if decision.decision == "idle":
            return decision

        if decision.decision == "reflect":
            synthesize_reflection(self.eventlog, meta_extra={"source": "autonomy_kernel"})
        elif decision.decision == "summarize":
            maybe_append_summary(self.eventlog)

        return decision
