"""Minimal runtime loop orchestrator for PMM v2."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.core.meme_graph import MemeGraph
from pmm.runtime.autonomy_kernel import AutonomyKernel, KernelDecision
from pmm.runtime.commitment_manager import CommitmentManager
from pmm.runtime.prompts import compose_system_prompt
from pmm.runtime.reflection import TurnDelta, build_reflection_text
from pmm.core.schemas import Claim
from pmm.core.validators import validate_claim
from pmm.core.semantic_extractor import extract_commitments, extract_claims
from pmm.runtime.context_builder import build_context
from pmm.runtime.autonomy_supervisor import AutonomySupervisor
from pmm.core.autonomy_tracker import AutonomyTracker
import asyncio
import threading
import time


DEBUG = False  # Set to True for debugging


class RuntimeLoop:
    def __init__(
        self,
        *,
        eventlog: EventLog,
        adapter,
        replay: bool = False,
        autonomy: bool = True,
    ) -> None:
        self.eventlog = eventlog
        self.mirror = Mirror(eventlog)
        self.memegraph = MemeGraph(eventlog)
        # wire event listeners
        self.eventlog.register_listener(self.mirror.sync)
        self.eventlog.register_listener(self.memegraph.add_event)
        self.commitments = CommitmentManager(eventlog)
        self.adapter = adapter
        self.replay = replay
        self.autonomy = AutonomyKernel(eventlog)
        self.tracker = AutonomyTracker(eventlog)
        if self.replay:
            self.mirror.rebuild()
            self.autonomy = AutonomyKernel(eventlog)
        if not self.replay:
            if not any(
                e["kind"] == "autonomy_rule_table" for e in self.eventlog.read_all()
            ):
                self.autonomy.ensure_rule_table_event()

            if autonomy:
                # Start autonomy supervisor
                epoch = "2025-11-01T00:00:00Z"  # Hardcoded for now
                interval_s = 10  # Hardcoded for testing
                self.supervisor = AutonomySupervisor(eventlog, epoch, interval_s)
                # LISTENER FIRST — catch every stimulus
                self.eventlog.register_listener(self._on_autonomy_stimulus)
                # THEN start the supervisor
                self._supervisor_thread = threading.Thread(
                    target=self._run_supervisor_async, daemon=True
                )
                self._supervisor_thread.start()

    def _run_supervisor_async(self) -> None:
        """Run the supervisor in an asyncio event loop."""
        asyncio.run(self.supervisor.run_forever())

    def _on_autonomy_stimulus(self, event: Dict[str, Any]) -> None:
        if DEBUG:
            print(f"[STIMULUS RECEIVED] id={event['id']} | kind={event['kind']}")
        if event.get("kind") == "autonomy_stimulus":
            try:
                payload = json.loads(event["content"])
                slot = payload.get("slot")
                slot_id = payload.get("slot_id")
                if slot is not None and slot_id:
                    if DEBUG:
                        print(f" → CALLING run_tick(slot={slot}, id={slot_id})")

                    def _delayed_tick() -> None:
                        time.sleep(0.2)
                        self.run_tick(slot=slot, slot_id=slot_id)

                    threading.Thread(target=_delayed_tick, daemon=True).start()
            except json.JSONDecodeError:
                if DEBUG:
                    print(" → [ERROR] Failed to parse autonomy_stimulus content")

    def _extract_commitments(self, text: str) -> List[str]:
        lines = (text or "").splitlines()
        return extract_commitments(lines)

    def _extract_closures(self, text: str) -> List[str]:
        cids: List[str] = []
        for line in (text or "").splitlines():
            if line.startswith("CLOSE:"):
                cids.append(line.split(":", 1)[1].strip())
        return cids

    def _extract_reflect(self, text: str) -> Dict[str, Any] | None:
        for line in (text or "").splitlines():
            if line.startswith("REFLECT:"):
                j = line[len("REFLECT:") :]
                try:
                    return json.loads(j)
                except Exception:
                    return None
        return None

    def _extract_claims(self, text: str) -> List[Claim]:
        lines = (text or "").splitlines()
        try:
            parsed = extract_claims(lines)
        except ValueError:
            # Keep runtime robust: skip malformed claim lines
            parsed = []
        return [Claim(type=ctype, data=data) for ctype, data in parsed]

    def _parse_ref_lines(self, content: str) -> None:
        refs: List[str] = []
        parsed: Dict[str, Any] | None = None
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            parsed = None

        if isinstance(parsed, dict) and isinstance(parsed.get("refs"), list):
            refs = [str(r) for r in parsed["refs"]]
        else:
            refs = [
                line[5:].strip()
                for line in content.splitlines()
                if line.startswith("REF: ")
            ]

        for ref in refs:
            if "#" not in ref:
                continue
            path, event_id_str = ref.split("#", 1)
            try:
                event_id = int(event_id_str)
            except ValueError:
                continue
            target_log = EventLog(path)
            target_event = target_log.get(event_id)
            if target_event:
                self.eventlog.append(
                    kind="inter_ledger_ref",
                    content=f"REF: {path}#{event_id}",
                    meta={"target_hash": target_event["hash"], "verified": True},
                )
            else:
                self.eventlog.append(
                    kind="inter_ledger_ref",
                    content=f"REF: {path}#{event_id}",
                    meta={"verified": False, "error": "not found"},
                )

    def run_turn(self, user_input: str) -> List[Dict[str, Any]]:
        if self.replay:
            # Replay mode: do not mutate ledger; simply return existing events.
            return self.eventlog.read_all()

        from pmm.runtime.reflection_synthesizer import synthesize_reflection
        from pmm.runtime.identity_summary import maybe_append_summary

        # 1. Log user message
        self.eventlog.append(
            kind="user_message", content=user_input, meta={"role": "user"}
        )

        # 2. Build prompts
        history = self.eventlog.read_tail(limit=10)
        open_comms = self.mirror.get_open_commitment_events()
        # Deterministic short context window
        ctx_block = build_context(self.eventlog, limit=5)
        base_prompt = compose_system_prompt(history, open_comms)
        system_prompt = f"{ctx_block}\n\n{base_prompt}" if ctx_block else base_prompt

        # 3. Invoke model
        t0 = time.perf_counter()
        assistant_reply = self.adapter.generate_reply(
            system_prompt=system_prompt, user_prompt=user_input
        )
        t1 = time.perf_counter()

        # 4. Log assistant message
        ai_event_id = self.eventlog.append(
            kind="assistant_message",
            content=assistant_reply,
            meta={"role": "assistant"},
        )

        # 4a. Parse REF: lines and append inter_ledger_ref events
        self._parse_ref_lines(assistant_reply)

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
                    kind="reflection",
                    content=reflection_text,
                    meta={"about_event": ai_event_id},
                )
                self._parse_ref_lines(reflection_text)

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
                events = self.run_turn(inp)
                # Print last assistant/reflection contents
                if self.replay:
                    # In replay, nothing new; just show last assistant/reflection in log
                    for e in events[::-1]:
                        if e["kind"] in ("assistant_message", "reflection"):
                            role = (
                                "Assistant"
                                if e["kind"] == "assistant_message"
                                else "Reflection"
                            )
                            print(f"{role}> {e['content']}")
                            break
                else:
                    # fresh turn appended; print the last assistant
                    last_ai = [e for e in events if e["kind"] == "assistant_message"][
                        -1
                    ]
                    # Hide COMMIT lines from user display (still logged in ledger)
                    lines = [
                        ln
                        for ln in (last_ai["content"] or "").splitlines()
                        if not ln.strip().upper().startswith("COMMIT:")
                    ]
                    assistant_output = "\n".join(lines)
                    print(f"Assistant> {assistant_output}")
        except (EOFError, KeyboardInterrupt):
            return

    def run_tick(self, *, slot: int, slot_id: str) -> KernelDecision:
        if DEBUG:
            print(f"[AUTONOMY TICK] slot={slot} | id={slot_id}")
        decision = self.autonomy.decide_next_action()
        if DEBUG:
            print(f" → DECISION: {decision.decision} | {decision.reasoning}")

        # Log the tick FIRST
        payload = json.dumps(decision.as_dict(), sort_keys=True, separators=(",", ":"))
        self.eventlog.append(
            kind="autonomy_tick",
            content=payload,
            meta={"source": "autonomy_kernel", "slot": slot, "slot_id": slot_id},
        )

        # THEN execute
        if decision.decision == "reflect":
            from pmm.runtime.reflection_synthesizer import synthesize_reflection

            # Pass the staleness threshold so the synthesizer can compute stale flags
            meta_extra = {
                "source": "autonomy_kernel",
                "slot_id": slot_id,
                "staleness_threshold": str(
                    self.autonomy.thresholds["commitment_staleness"]
                ),
                "auto_close_threshold": str(
                    self.autonomy.thresholds["commitment_auto_close"]
                ),
            }
            reflection_id = synthesize_reflection(
                self.eventlog,
                meta_extra=meta_extra,
                staleness_threshold=int(meta_extra["staleness_threshold"]),
                auto_close_threshold=int(meta_extra["auto_close_threshold"]),
            )
            if reflection_id:
                target_event = self.eventlog.get(reflection_id)
                self._parse_ref_lines(target_event["content"])
        elif decision.decision == "summarize":
            from pmm.runtime.identity_summary import maybe_append_summary

            maybe_append_summary(self.eventlog)

        return decision
