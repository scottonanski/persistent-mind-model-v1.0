# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/loop.py
"""Minimal runtime loop orchestrator for PMM v2."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pmm.adapters import AdapterTransportError, normalize_generation_result
from pmm.core.event_log import EventLog, TERMINAL_OUTCOME_PROTOCOL
from pmm.core.mirror import Mirror
from pmm.core.meme_graph import MemeGraph
from pmm.core.commitment_manager import CommitmentManager
from pmm.core.schemas import Claim
from pmm.core.validators import (
    ClaimValidationResult,
    validate_claim_detailed,
    validate_evidence_designations,
)
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
from pmm.core.identity_manager import maybe_append_identity_adoptions
from pmm.runtime.reflection import TurnDelta, build_reflection_text
from pmm.retrieval.pipeline import run_retrieval_pipeline, RetrievalConfig
from pmm.runtime.context_renderer import render_context_with_metrics
from pmm.runtime.prompts import SYSTEM_PRIMER
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
    _PROMPT_MEASUREMENT_TRANSPORT_FIELDS = {
        "adapter_system_primer_insertions",
        "total_assembled_prompt_chars",
        "provider_prompt_tokens",
        "context_window_tokens",
    }

    @classmethod
    def _build_output_telemetry(
        cls, generation_meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize conservative provider output measurements."""

        meta = generation_meta if isinstance(generation_meta, dict) else {}
        stop_reason = meta.get("provider_stop_reason")
        if not isinstance(stop_reason, str) or not stop_reason:
            stop_reason = None
        return {
            "schema": "output_telemetry.v1",
            "configured_output_budget_tokens": cls._optional_positive_int(
                meta.get("configured_output_budget_tokens")
            ),
            "provider_output_tokens": cls._optional_nonnegative_int(
                meta.get("provider_output_tokens")
            ),
            "provider_reasoning_tokens": cls._optional_nonnegative_int(
                meta.get("provider_reasoning_tokens")
            ),
            "provider_stop_reason": stop_reason,
            "length_limit_reached": bool(meta.get("length_limit_reached")),
        }

    @staticmethod
    def _optional_nonnegative_int(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    @staticmethod
    def _optional_positive_int(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return None

    @classmethod
    def _build_prompt_telemetry(
        cls,
        *,
        context_chars: int,
        provenance_chars: int,
        evidence_chars: int,
        user_message_chars: int,
        selected_evidence_events: int,
        generation_meta: Dict[str, Any],
        adapter_context_window_tokens: Any = None,
    ) -> Dict[str, Any]:
        """Normalize content-free prompt measurements for one generation."""

        meta = generation_meta if isinstance(generation_meta, dict) else {}
        adapter_insertions = cls._optional_nonnegative_int(
            meta.get("adapter_system_primer_insertions")
        )
        system_primer_insertions = 1 + (adapter_insertions or 0)
        provider_prompt_tokens = cls._optional_nonnegative_int(
            meta.get("provider_prompt_tokens")
        )
        if provider_prompt_tokens is None:
            provider_prompt_tokens = cls._optional_nonnegative_int(
                meta.get("prompt_eval_count")
            )
        context_window_tokens = cls._optional_positive_int(
            meta.get("context_window_tokens")
        )
        if context_window_tokens is None:
            context_window_tokens = cls._optional_positive_int(
                adapter_context_window_tokens
            )

        return {
            "schema": "prompt_telemetry.v1",
            "system_primer_insertions": system_primer_insertions,
            "system_primer_chars": system_primer_insertions * len(SYSTEM_PRIMER),
            "rendered_pmm_context_chars": context_chars,
            "retrieval_provenance_chars": provenance_chars,
            "raw_evidence_chars": evidence_chars,
            "user_message_chars": user_message_chars,
            "total_assembled_prompt_chars": cls._optional_nonnegative_int(
                meta.get("total_assembled_prompt_chars")
            ),
            "selected_evidence_events": selected_evidence_events,
            "provider_prompt_tokens": provider_prompt_tokens,
            "context_window_tokens": context_window_tokens,
        }

    @classmethod
    def _remove_prompt_measurement_transport(cls, meta: Dict[str, Any]) -> None:
        for field in cls._PROMPT_MEASUREMENT_TRANSPORT_FIELDS:
            meta.pop(field, None)

    def __init__(
        self,
        *,
        eventlog: EventLog,
        adapter,
        replay: bool = False,
        autonomy: bool = True,
        thresholds: Optional[Dict[str, int]] = None,
        output_budget_tokens: int | None = None,
    ) -> None:
        configured_budget = (
            output_budget_tokens
            if output_budget_tokens is not None
            else getattr(adapter, "output_budget_tokens", None)
        )
        if configured_budget is not None:
            if self._optional_positive_int(configured_budget) is None:
                raise ValueError("output budget must be a positive integer")
            if getattr(adapter, "supports_output_budget", False) is not True:
                raise ValueError(
                    "configured output budget is unsupported by selected adapter"
                )
            if getattr(adapter, "output_budget_tokens", None) != configured_budget:
                raise ValueError("selected adapter did not accept the output budget")
        self.eventlog = eventlog
        if not replay:
            self._recover_latest_interrupted_turn()
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

    def _recover_latest_interrupted_turn(self) -> int | None:
        """Recover only an unambiguous latest managed turn, if one exists."""

        events = self.eventlog.read_all()
        latest_user_index = next(
            (
                index
                for index in range(len(events) - 1, -1, -1)
                if events[index].get("kind") == "user_message"
            ),
            None,
        )
        if latest_user_index is None:
            return None
        user_event = events[latest_user_index]
        user_meta = user_event.get("meta") or {}
        if user_meta.get("turn_protocol") != TERMINAL_OUTCOME_PROTOCOL:
            return None

        user_event_id = int(user_event["id"])
        suffix = events[latest_user_index + 1 :]
        for event in suffix:
            meta = event.get("meta") or {}
            if (
                event.get("kind") in {"assistant_message", "generation_failure"}
                and meta.get("turn_protocol") == TERMINAL_OUTCOME_PROTOCOL
                and meta.get("about_event") == user_event_id
            ):
                return None

        for event in suffix:
            if event.get("kind") != "embedding_add":
                return None
            try:
                embedded_event_id = json.loads(event.get("content") or "{}").get(
                    "event_id"
                )
            except (TypeError, json.JSONDecodeError):
                return None
            if embedded_event_id != user_event_id:
                return None

        failure_id, _ = self.eventlog.append_terminal_outcome(
            user_event_id=user_event_id,
            kind="generation_failure",
            content="",
            meta={"source": "runtime_recovery", "status": "interrupted"},
        )
        return failure_id

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
            kind="user_message",
            content=user_input,
            meta={
                "role": "user",
                "turn_protocol": TERMINAL_OUTCOME_PROTOCOL,
            },
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
        total_events = self.eventlog.count()
        meditation_active = total_events > 20 and total_events % 37 == 0
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

        context_render = render_context_with_metrics(
            result=retrieval_result,
            eventlog=self.eventlog,
            concept_graph=self.concept_graph,
            meme_graph=self.memegraph,
            mirror=self.mirror,
        )
        ctx_block = context_render.text

        selection_ids = retrieval_result.event_ids
        selection_provenance = retrieval_result.provenance
        selection_scores = [
            float(
                (selection_provenance.get(event_id, {}).get("scores") or {}).get(
                    "vector", 0.0
                )
            )
            for event_id in selection_ids
        ]

        # Check if graph context is actually present
        context_has_graph = "## Graph" in ctx_block
        base_prompt = compose_system_prompt(
            history,
            open_comms,
            context_has_graph=context_has_graph,
            history_len=total_events,
        )
        system_prompt = f"{ctx_block}\n\n{base_prompt}" if ctx_block else base_prompt

        # 3. Invoke model
        t0 = time.perf_counter()
        try:
            generation_result = normalize_generation_result(
                self.adapter.generate_reply(
                    system_prompt=system_prompt, user_prompt=user_input
                )
            )
        except AdapterTransportError as exc:
            failure_meta = dict(exc.meta)
            failure_meta.setdefault(
                "configured_output_budget_tokens",
                getattr(self.adapter, "output_budget_tokens", None),
            )
            prompt_telemetry = self._build_prompt_telemetry(
                context_chars=len(ctx_block),
                provenance_chars=context_render.retrieval_provenance_chars,
                evidence_chars=context_render.raw_evidence_chars,
                user_message_chars=len(user_input),
                selected_evidence_events=len(selection_ids),
                generation_meta=failure_meta,
                adapter_context_window_tokens=getattr(
                    self.adapter, "context_window_tokens", None
                ),
            )
            self._remove_prompt_measurement_transport(failure_meta)
            output_telemetry = self._build_output_telemetry(failure_meta)
            failure_meta.update(
                {
                    "source": "runtime",
                    "status": "transport_error",
                    "reason_code": "ADAPTER_TRANSPORT_ERROR",
                    "error_category": exc.category,
                    "prompt_telemetry": prompt_telemetry,
                    "output_telemetry": output_telemetry,
                }
            )
            self.eventlog.append_terminal_outcome(
                user_event_id=user_event_id,
                kind="generation_failure",
                content="",
                meta=failure_meta,
            )
            return self.eventlog.read_since(user_event_id - 1, limit=200)
        except Exception as exc:
            output_meta = {
                "configured_output_budget_tokens": getattr(
                    self.adapter, "output_budget_tokens", None
                )
            }
            prompt_telemetry = self._build_prompt_telemetry(
                context_chars=len(ctx_block),
                provenance_chars=context_render.retrieval_provenance_chars,
                evidence_chars=context_render.raw_evidence_chars,
                user_message_chars=len(user_input),
                selected_evidence_events=len(selection_ids),
                generation_meta=output_meta,
                adapter_context_window_tokens=getattr(
                    self.adapter, "context_window_tokens", None
                ),
            )
            self.eventlog.append_terminal_outcome(
                user_event_id=user_event_id,
                kind="generation_failure",
                content="",
                meta={
                    "source": "runtime",
                    "status": "transport_error",
                    "reason_code": "ADAPTER_EXCEPTION",
                    "error_category": type(exc).__name__,
                    "prompt_telemetry": prompt_telemetry,
                    "output_telemetry": self._build_output_telemetry(output_meta),
                },
            )
            return self.eventlog.read_since(user_event_id - 1, limit=200)
        t1 = time.perf_counter()
        assistant_reply = generation_result.text
        prompt_telemetry = self._build_prompt_telemetry(
            context_chars=len(ctx_block),
            provenance_chars=context_render.retrieval_provenance_chars,
            evidence_chars=context_render.raw_evidence_chars,
            user_message_chars=len(user_input),
            selected_evidence_events=len(selection_ids),
            generation_meta=generation_result.meta,
            adapter_context_window_tokens=getattr(
                self.adapter, "context_window_tokens", None
            ),
        )
        output_meta = dict(generation_result.meta)
        output_meta.setdefault(
            "configured_output_budget_tokens",
            getattr(self.adapter, "output_budget_tokens", None),
        )
        output_telemetry = self._build_output_telemetry(output_meta)

        # Failed or incomplete generations are diagnostic events only. They must
        # never become assistant messages or reach semantic state parsers.
        if generation_result.status != "complete":
            failure_meta: Dict[str, Any] = {
                "source": "runtime",
                "status": generation_result.status,
            }
            failure_meta.update(generation_result.meta)
            self._remove_prompt_measurement_transport(failure_meta)
            failure_meta["prompt_telemetry"] = prompt_telemetry
            failure_meta["output_telemetry"] = output_telemetry
            self.eventlog.append_terminal_outcome(
                user_event_id=user_event_id,
                kind="generation_failure",
                content=assistant_reply,
                meta=failure_meta,
            )
            return self.eventlog.read_since(user_event_id - 1, limit=200)

        # 3a. Try to parse optional structured JSON header (intent/outcome/etc. + concepts).
        #     Expected pattern in test mode: first line is a JSON object, followed
        #     by normal free-text. We leave assistant_reply unchanged and only
        #     record a normalized payload + concepts for CTL indexing.
        structured_payload: Optional[str] = None
        active_concepts: List[str] = []
        designation_validation: ClaimValidationResult | None = None
        evidence_designations: List[dict] = []
        attempted_evidence_designations: Any = None
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
                if "evidence_designations" in parsed:
                    attempted_evidence_designations = parsed["evidence_designations"]
                    designation_validation, evidence_designations = (
                        validate_evidence_designations(
                            attempted_evidence_designations, selection_ids
                        )
                    )
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

        # Deterministic ontological concept seeding fallback during meditations
        if meditation_active and not active_concepts:
            active_concepts.extend(
                ["ontology.structure", "identity.evolution", "awareness.loop"]
            )

        # Universal continuity fallback: ensure every turn has at least one concept binding
        # This prevents orphaned events and strengthens narrative continuity in ConceptGraph
        if not active_concepts:
            active_concepts = ["identity.continuity"]

        # 4. Log assistant message (content preserved; optional structured/concept meta)
        ai_meta: Dict[str, Any] = {"role": "assistant"}
        if structured_payload is not None:
            ai_meta["assistant_structured"] = True
            ai_meta["assistant_schema"] = "assistant.v1"
            ai_meta["assistant_payload"] = structured_payload
        # Include metadata carried by this specific generation result.
        if isinstance(generation_result.meta, dict):
            for k, v in generation_result.meta.items():
                if k in self._PROMPT_MEASUREMENT_TRANSPORT_FIELDS:
                    continue
                ai_meta[k] = v
        if designation_validation is not None and designation_validation.ok:
            # Validated runtime metadata is authoritative over provider metadata.
            ai_meta["evidence_designations_validated"] = True
            ai_meta["evidence_designations"] = evidence_designations
        ai_event_id, terminal_created = self.eventlog.append_terminal_outcome(
            user_event_id=user_event_id,
            kind="assistant_message",
            content=assistant_reply,
            meta=ai_meta,
        )
        if not terminal_created:
            return self.eventlog.read_since(user_event_id - 1, limit=200)

        if designation_validation is not None and not designation_validation.ok:
            failure_content = json.dumps(
                {
                    "validation_type": "evidence_designation",
                    "data": {
                        "evidence_designations": attempted_evidence_designations
                    },
                    "reason_code": designation_validation.code,
                    "reason": designation_validation.message,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            self.eventlog.append(
                kind="validation_failure",
                content=failure_content,
                meta={
                    "source": "evidence_designation_validator",
                    "about_event": ai_event_id,
                    "reason_code": designation_validation.code,
                },
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
                    "provenance": [
                        {
                            "event_id": event_id,
                            **selection_provenance.get(
                                event_id, {"reasons": [], "scores": {}}
                            ),
                        }
                        for event_id in selection_ids
                    ],
                    "strategy": "hybrid",
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
        self.eventlog.append(
            kind="metrics_turn",
            content=diag,
            meta={
                "prompt_telemetry": prompt_telemetry,
                "output_telemetry": output_telemetry,
            },
        )

        # 4d. Synthesize deterministic reflection and maybe append summary
        synthesize_reflection(self.eventlog, mirror=self.mirror)
        maybe_append_summary(self.eventlog)
        maybe_append_lifetime_memory(self.eventlog, self.concept_graph, self.memegraph)

        delta = TurnDelta()

        # 5. Commitments (open)
        for c in self._extract_commitments(assistant_reply):
            cid = self.commitments.open_commitment(c, source="assistant")
            if cid:
                delta.opened.append(cid)
                extract_exec_binds(self.eventlog, c, cid)

                # Bind concepts to this thread/CID for thread-first retrieval.
                if active_concepts:
                    existing = set(
                        self.concept_graph.resolve_cids_for_concepts(active_concepts)
                    )
                    for token in active_concepts:
                        if cid in existing:
                            continue
                        bind_content = json.dumps(
                            {
                                "cid": cid,
                                "tokens": [token],
                                "relation": "relevant_to",
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        self.eventlog.append(
                            kind="concept_bind_thread",
                            content=bind_content,
                            meta={"source": "loop"},
                        )

        if self.exec_router is not None:
            self.exec_router.tick()

        # 6. Claims
        for claim in self._extract_claims(assistant_reply):
            validation = validate_claim_detailed(
                claim,
                self.eventlog,
                self.mirror,
                selected_event_ids=selection_ids,
            )
            if validation.ok:
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
                failure_content = json.dumps(
                    {
                        "claim_type": claim.type,
                        "data": claim.data,
                        "reason_code": validation.code,
                        "reason": validation.message,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                self.eventlog.append(
                    kind="validation_failure",
                    content=failure_content,
                    meta={
                        "source": "claim_validator",
                        "about_event": ai_event_id,
                        "claim_type": claim.type,
                        "reason_code": validation.code,
                    },
                )
                delta.failed_claims.append(claim)

        # 6a. Identity adoption – derive from validated identity_* CLAIMs.
        # This is ledger-only, deterministic, and idempotent.
        maybe_append_identity_adoptions(self.eventlog)

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
