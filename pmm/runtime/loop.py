# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/loop.py
"""Minimal runtime loop orchestrator for PMM v2."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.core.meme_graph import MemeGraph
from pmm.core.commitment_manager import CommitmentManager
from pmm.core.schemas import Claim
from pmm.core.validators import validate_claim
from pmm.core.semantic_extractor import (
    extract_commitments,
    extract_claims,
    extract_closures,
    extract_reflect,
)
from pmm.core.concept_graph import ConceptGraph
from pmm.core.concept_ops_compiler import compile_assistant_message_concepts
from pmm.commitments.binding import extract_exec_binds
from pmm.runtime.autonomy_kernel import AutonomyKernel, KernelDecision
from pmm.runtime.prompts import compose_system_prompt
from pmm.runtime.reflection import TurnDelta, build_reflection_text
from pmm.retrieval.pipeline import run_retrieval_pipeline, RetrievalConfig
from pmm.runtime.context_renderer import render_context
from pmm.retrieval.vector import (
    selection_digest,
    ensure_embedding_for_event,
)
from pmm.runtime.bindings import ExecBindRouter
from pmm.runtime.autonomy_supervisor import AutonomySupervisor
from pmm.core.autonomy_tracker import AutonomyTracker
from pmm.learning.outcome_tracker import build_outcome_observation_content
from pmm.runtime.indexer import Indexer
from pmm.runtime.ctl_injector import CTLLookupInjector
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
        thresholds: Optional[Dict[str, int]] = None,
    ) -> None:
        self.eventlog = eventlog
        self.mirror = Mirror(eventlog)
        self.memegraph = MemeGraph(eventlog)
        # wire event listeners
        self.eventlog.register_listener(self.mirror.sync)
        self.eventlog.register_listener(self.memegraph.add_event)
        # ConceptGraph projection for CTL (rebuildable and listener-backed)
        self.concept_graph = ConceptGraph(eventlog)
        # Seed from existing events (if any), then listen for updates
        self.concept_graph.rebuild()
        self.eventlog.register_listener(self.concept_graph.sync)
        self.commitments = CommitmentManager(eventlog)
        self.adapter = adapter
        self.replay = replay
        self.autonomy = AutonomyKernel(eventlog, thresholds=thresholds)
        self.tracker = AutonomyTracker(eventlog)
        self.indexer = Indexer(eventlog)
        self.ctl_injector = CTLLookupInjector(self.concept_graph)
        self.exec_router: ExecBindRouter | None = None
        if self.replay:
            self.mirror.rebuild()
            self.autonomy = AutonomyKernel(eventlog)
        if not self.replay:
            self.exec_router = ExecBindRouter(eventlog)
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
        lines = (text or "").splitlines()
        candidates = extract_closures(lines)
        return [c for c in candidates if self._valid_cid(c)]

    @staticmethod
    def _valid_cid(cid: str) -> bool:
        """Return True for any non-empty CID (legacy-compatible).

        Rationale: commitments may use short test CIDs (e.g., "abcd"),
        internal CIDs (mc_000123), or 8-hex derived IDs. To preserve
        backward compatibility and avoid rejecting valid closures, accept
        any non-empty, stripped string here. Deterministic validation of
        structure can be added later without breaking tests.
        """
        return bool((cid or "").strip())

    def _extract_reflect(self, text: str) -> Dict[str, Any] | None:
        lines = (text or "").splitlines()
        return extract_reflect(lines)

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
        from pmm.runtime.lifetime_memory import maybe_append_lifetime_memory

        # 1. Log user message
        user_event_id = self.eventlog.append(
            kind="user_message", content=user_input, meta={"role": "user"}
        )
        # If vector retrieval is enabled, append embedding_add for the user message (idempotent)
        retrieval_cfg = self.mirror.current_retrieval_config or {}
        if retrieval_cfg and retrieval_cfg.get("strategy") == "vector":
            model = str(retrieval_cfg.get("model", "hash64"))
            dims = int(retrieval_cfg.get("dims", 64))
            ensure_embedding_for_event(
                events=[],
                eventlog=self.eventlog,
                event_id=user_event_id,
                text=user_input,
                model=model,
                dims=dims,
            )

        # 2. Build prompts
        history = self.eventlog.read_tail(limit=10)
        open_comms = self.mirror.get_open_commitment_events()

        # Configure and run Retrieval Pipeline
        pipeline_config = RetrievalConfig()

        # CTL Lookup Injection: Identify concepts in query and force their inclusion
        injected_tokens = self.ctl_injector.extract_tokens(user_input)
        pipeline_config.sticky_concepts.extend(injected_tokens)

        if retrieval_cfg:
            try:
                limit_val = int(retrieval_cfg.get("limit", 20))
                if limit_val > 0:
                    pipeline_config.limit_total_events = limit_val
            except (ValueError, TypeError):
                pass

            if retrieval_cfg.get("strategy") == "vector":
                pipeline_config.enable_vector_search = True
            elif retrieval_cfg.get("strategy") == "fixed":
                # "fixed" implies relying on limit, usually no vector?
                # But fixed means "fixed window".
                # The new pipeline is always graph/concept aware.
                # If we want to support pure fixed window, we would need to bypass.
                # But the proposal says "Consolidate CTL... Legacy cleanup".
                # So we can interpret "fixed" as just limiting size but still using concepts.
                # Or we can disable vector search for fixed.
                pipeline_config.enable_vector_search = False

        user_event = self.eventlog.get(user_event_id)

        retrieval_result = run_retrieval_pipeline(
            query_text=user_input,
            eventlog=self.eventlog,
            concept_graph=self.concept_graph,
            meme_graph=self.memegraph,
            config=pipeline_config,
            user_event=user_event,
        )

        ctx_block = render_context(
            result=retrieval_result,
            eventlog=self.eventlog,
            concept_graph=self.concept_graph,
            meme_graph=self.memegraph,
            mirror=self.mirror,
        )

        selection_ids = retrieval_result.event_ids
        # We don't calculate vector scores in pipeline result yet, so pass empty/dummy
        selection_scores = [0.0] * len(selection_ids)

        # Check if graph context is actually present (Threads or Concepts sections)
        context_has_graph = "## Threads" in ctx_block or "## Concepts" in ctx_block
        base_prompt = compose_system_prompt(
            history, open_comms, context_has_graph=context_has_graph
        )
        system_prompt = f"{ctx_block}\n\n{base_prompt}" if ctx_block else base_prompt

        # 3. Invoke model
        t0 = time.perf_counter()
        assistant_reply = self.adapter.generate_reply(
            system_prompt=system_prompt, user_prompt=user_input
        )
        t1 = time.perf_counter()

        # 3a. Try to parse optional structured JSON header (intent/outcome/etc. + concepts).
        #     Expected pattern in test mode: first line is a JSON object, followed
        #     by normal free-text. We leave assistant_reply unchanged and only
        #     record a normalized payload + concepts for CTL indexing.
        structured_payload: Optional[str] = None
        active_concepts: List[str] = []
        try:
            reply_str = assistant_reply or ""
            # Prefer a JSON header on the first line if present; fall back to
            # parsing the whole reply when there is a single-line payload.
            if "\n" in reply_str:
                # split once into leading line + remainder
                parts = reply_str.split("\n", 1)
                header_line = parts[0]
            else:
                header_line = reply_str
            parsed = json.loads(header_line)
            if isinstance(parsed, dict):
                # Structured control payload
                if all(
                    k in parsed for k in ("intent", "outcome", "next", "self_model")
                ) and all(
                    isinstance(parsed[k], str)
                    for k in ("intent", "outcome", "next", "self_model")
                ):
                    structured_payload = json.dumps(
                        parsed, sort_keys=True, separators=(",", ":")
                    )
                # Optional Active Concepts for CTL indexing
                concepts_val = parsed.get("concepts")
                if isinstance(concepts_val, list):
                    active_concepts = [
                        str(c).strip()
                        for c in concepts_val
                        if isinstance(c, str) and str(c).strip()
                    ]
        except (TypeError, json.JSONDecodeError):
            structured_payload = None
            active_concepts = []

        # 4. Log assistant message (content preserved; optional structured/concept meta)
        ai_meta: Dict[str, Any] = {"role": "assistant"}
        if structured_payload is not None:
            ai_meta["assistant_structured"] = True
            ai_meta["assistant_schema"] = "assistant.v1"
            ai_meta["assistant_payload"] = structured_payload
        # Include deterministic generation metadata from adapters if present
        gen_meta = getattr(self.adapter, "generation_meta", None)
        if isinstance(gen_meta, dict):
            for k, v in gen_meta.items():
                ai_meta[k] = v
        ai_event_id = self.eventlog.append(
            kind="assistant_message",
            content=assistant_reply,
            meta=ai_meta,
        )

        # 4a. Active Indexing: bind this turn's events to any model-emitted concepts.
        if active_concepts:
            turn_event_ids = [user_event_id, ai_event_id]
            for token in active_concepts:
                # Idempotent binding via ConceptGraph projection.
                existing = set(self.concept_graph.events_for_concept(token))
                for eid in turn_event_ids:
                    if eid in existing:
                        continue
                    bind_content = json.dumps(
                        {
                            "event_id": eid,
                            "tokens": [token],
                            "relation": "relevant_to",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    self.eventlog.append(
                        kind="concept_bind_event",
                        content=bind_content,
                        meta={"source": "active_indexing"},
                    )
        # Compile any structured CTL concept_ops from this assistant message.
        # This is deterministic and no-op when concept_ops is absent.
        assistant_event = self.eventlog.get(ai_event_id)
        if assistant_event is not None:
            compile_assistant_message_concepts(
                self.eventlog,
                self.concept_graph,
                assistant_event,
            )
        # If vector retrieval, append embedding for assistant message (idempotent)
        if retrieval_cfg and retrieval_cfg.get("strategy") == "vector":
            model = str(retrieval_cfg.get("model", "hash64"))
            dims = int(retrieval_cfg.get("dims", 64))
            ensure_embedding_for_event(
                events=[],
                eventlog=self.eventlog,
                event_id=ai_event_id,
                text=assistant_reply,
                model=model,
                dims=dims,
            )

        # 4a. Parse REF: lines and append inter_ledger_ref events
        self._parse_ref_lines(assistant_reply)

        # 4b. If vector retrieval was used, append retrieval_selection event
        if selection_ids is not None and selection_scores is not None:
            # Build provenance digest for auditability
            model = str((retrieval_cfg or {}).get("model", "hash64"))
            dims = int((retrieval_cfg or {}).get("dims", 64))
            dig = selection_digest(
                selected=selection_ids,
                scores=selection_scores,
                model=model,
                dims=dims,
                query_text=user_input,
            )
            sel_content = json.dumps(
                {
                    "turn_id": ai_event_id,
                    "selected": selection_ids,
                    "scores": selection_scores,
                    "strategy": "vector",
                    "model": model,
                    "dims": dims,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            self.eventlog.append(
                kind="retrieval_selection", content=sel_content, meta={"digest": dig}
            )

        # 4c. Per-turn diagnostics (deterministic formatting)
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

        # 4d. Synthesize deterministic reflection and maybe append summary
        synthesize_reflection(self.eventlog, mirror=self.mirror)
        maybe_append_summary(self.eventlog)
        maybe_append_lifetime_memory(self.eventlog, self.concept_graph)

        delta = TurnDelta()

        # 5. Commitments (open)
        for c in self._extract_commitments(assistant_reply):
            cid = self.commitments.open_commitment(c, source="assistant")
            if cid:
                delta.opened.append(cid)
                extract_exec_binds(self.eventlog, c, cid)

        if self.exec_router is not None:
            self.exec_router.tick()

        # 6. Claims
        for claim in self._extract_claims(assistant_reply):
            ok, _msg = validate_claim(claim, self.eventlog, self.mirror)
            if ok:
                # Persist valid claims to ledger for future retrieval
                claim_content = (
                    f"CLAIM:{claim.type}="
                    f"{json.dumps(claim.data, sort_keys=True, separators=(',', ':'))}"
                )
                claim_event_id = self.eventlog.append(
                    kind="claim",
                    content=claim_content,
                    meta={"claim_type": claim.type, "validated": True},
                )
                # Auto-bind all validated claims into CTL for long-term recall
                target_token = claim.type
                already_bound = claim_event_id in self.concept_graph.events_for_concept(
                    target_token
                )
                if not already_bound:
                    bind_content = json.dumps(
                        {
                            "event_id": claim_event_id,
                            "tokens": [target_token],
                            "relation": "describes",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    self.eventlog.append(
                        kind="concept_bind_event",
                        content=bind_content,
                        meta={"source": "auto_binder"},
                    )
            else:
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

        return self.eventlog.read_tail(limit=200)

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
                        if not extract_commitments([ln.upper()])
                    ]
                    assistant_output = "\n".join(lines)
                    print(f"Assistant> {assistant_output}")
        except (EOFError, KeyboardInterrupt):
            return

    def run_tick(self, *, slot: int, slot_id: str) -> KernelDecision:
        if DEBUG:
            print(f"[AUTONOMY TICK] slot={slot} | id={slot_id}")
        # Snapshot ledger before decision for outcome analysis
        events_before = self.eventlog.read_tail(limit=200)
        last_id_before = events_before[-1]["id"] if events_before else 0

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
                autonomy=self.autonomy,
            )
            if reflection_id:
                target_event = self.eventlog.get(reflection_id)
                self._parse_ref_lines(target_event["content"])
        elif decision.decision == "summarize":
            from pmm.runtime.identity_summary import maybe_append_summary

            maybe_append_summary(self.eventlog)
        elif decision.decision == "index":
            self.indexer.run_indexing_cycle()

        if self.exec_router is not None:
            self.exec_router.tick()

        # After executing the decision, emit per-tick outcome observation and
        # invoke adaptive metrics/learning in the autonomy kernel.
        events_after = self.eventlog.read_tail(limit=200)
        self._emit_tick_outcome_and_adapt(
            decision=decision,
            last_id_before=last_id_before,
            events_after=events_after,
            slot=slot,
            slot_id=slot_id,
        )

        return decision

    def _emit_tick_outcome_and_adapt(
        self,
        *,
        decision: KernelDecision,
        last_id_before: int,
        events_after: List[Dict[str, Any]],
        slot: int,
        slot_id: str,
    ) -> None:
        """Emit outcome_observation for this autonomy tick and adapt."""
        # Events that occurred as a result of this tick (including autonomy_tick)
        events_since = [e for e in events_after if int(e.get("id", 0)) > last_id_before]

        # Determine observed_result based on whether the intended action actually
        # produced its corresponding ledger events.
        observed_result = "success"
        if decision.decision == "reflect":
            has_reflection = any(
                e.get("kind") == "reflection"
                and (e.get("meta") or {}).get("source") == "autonomy_kernel"
                for e in events_since
            )
            observed_result = "success" if has_reflection else "no_delta"
        elif decision.decision == "summarize":
            has_summary = any(e.get("kind") == "summary_update" for e in events_since)
            observed_result = "success" if has_summary else "no_delta"
        elif decision.decision == "index":
            has_index = any(
                e.get("kind") in ("claim_from_text", "concept_bind_async")
                for e in events_since
            )
            observed_result = "success" if has_index else "no_delta"

        # Encode action_kind as autonomy_<decision> for learning metrics.
        action_kind = f"autonomy_{decision.decision}"
        commitment_id = ""
        action_payload = f"decision={decision.decision}"
        evidence_event_ids = [int(e.get("id", 0)) for e in events_since][-10:]

        content_dict = build_outcome_observation_content(
            commitment_id=commitment_id,
            action_kind=action_kind,
            action_payload=action_payload,
            observed_result=observed_result,
            evidence_event_ids=evidence_event_ids,
        )
        self.eventlog.append(
            kind="outcome_observation",
            content=json.dumps(content_dict, sort_keys=True, separators=(",", ":")),
            meta={"source": "autonomy_kernel", "slot": slot, "slot_id": slot_id},
        )

        # Invoke adaptive telemetry/learning for this tick. These helpers are
        # deterministic and idempotent over the ledger.
        self.autonomy._maybe_emit_stability_metrics()
        self.autonomy._maybe_emit_coherence_check()
        self.autonomy._maybe_emit_meta_policy_update()
        self.autonomy._maybe_emit_policy_update()
        # Maintain CTL bindings as part of autonomy maintenance, keeping CTL
        # fully automatic and PMM-internal while reusing the shared
        # ConceptGraph projection instead of rebuilding from scratch.
        self.autonomy._maybe_maintain_concepts(events_after, self.concept_graph)
