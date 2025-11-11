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
from pmm.runtime.autonomy_kernel import AutonomyKernel, KernelDecision
from pmm.core.commitment_manager import CommitmentManager
from pmm.runtime.prompts import compose_system_prompt
from pmm.runtime.reflection import TurnDelta, build_reflection_text
from pmm.core.schemas import Claim
from pmm.core.validators import validate_claim
from pmm.core.semantic_extractor import extract_commitments, extract_claims
from pmm.commitments.binding import extract_exec_binds
from pmm.runtime.context_builder import build_context, _last_retrieval_config
from pmm.retrieval.vector import (
    select_by_vector,
    build_context_from_ids,
    selection_digest,
    ensure_embedding_for_event,
    build_index,
)
from pmm.runtime.bindings import ExecBindRouter
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
        thresholds: Optional[Dict[str, int]] = None,
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
        self.autonomy = AutonomyKernel(eventlog, thresholds=thresholds)
        self.tracker = AutonomyTracker(eventlog)
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
        cids: List[str] = []
        for line in (text or "").splitlines():
            if line.startswith("CLOSE:"):
                candidate = line.split(":", 1)[1].strip()
                if self._valid_cid(candidate):
                    cids.append(candidate)
        return cids

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
        user_event_id = self.eventlog.append(
            kind="user_message", content=user_input, meta={"role": "user"}
        )
        # If vector retrieval is enabled, append embedding_add for the user message (idempotent)
        retrieval_cfg = _last_retrieval_config(self.eventlog)
        if retrieval_cfg and retrieval_cfg.get("strategy") == "vector":
            model = str(retrieval_cfg.get("model", "hash64"))
            dims = int(retrieval_cfg.get("dims", 64))
            ensure_embedding_for_event(
                events=self.eventlog.read_all(),
                eventlog=self.eventlog,
                event_id=user_event_id,
                text=user_input,
                model=model,
                dims=dims,
            )

        # 2. Build prompts
        history = self.eventlog.read_tail(limit=10)
        open_comms = self.mirror.get_open_commitment_events()
        # Deterministic retrieval: fixed (default) or vector (Phase 1)
        ctx_block = ""
        selection_ids: List[int] | None = None
        selection_scores: List[float] | None = None
        if retrieval_cfg and retrieval_cfg.get("strategy") == "vector":
            try:
                limit = int(retrieval_cfg.get("limit", 5))
            except Exception:
                limit = 5
            model = str(retrieval_cfg.get("model", "hash64"))
            dims_raw = retrieval_cfg.get("dims", 64)
            try:
                dims = int(dims_raw)
            except Exception:
                dims = 64
            events_full = self.eventlog.read_all()
            # Prefer stored embeddings when present; fall back to on-the-fly
            index = build_index(events_full, model=model, dims=dims)
            if index:
                from pmm.retrieval.vector import (
                    DeterministicEmbedder,
                    cosine,
                    candidate_messages,
                )

                qv = DeterministicEmbedder(model=model, dims=dims).embed(user_input)
                cands = candidate_messages(events_full)
                scored: List[tuple[int, float]] = []
                for ev in cands:
                    eid = int(ev.get("id", 0))
                    vec = index.get(eid)
                    if vec is None:
                        vec = DeterministicEmbedder(model=model, dims=dims).embed(
                            ev.get("content") or ""
                        )
                    s = cosine(qv, vec)
                    scored.append((eid, s))
                scored.sort(key=lambda t: (-t[1], t[0]))
                top = scored[:limit]
                ids = [eid for (eid, _s) in top]
                scores = [float(f"{_s:.6f}") for (_eid, _s) in top]
            else:
                ids, scores = select_by_vector(
                    events=events_full,
                    query_text=user_input,
                    limit=limit,
                    model=model,
                    dims=dims,
                )
            ctx_block = build_context_from_ids(events_full, ids, eventlog=self.eventlog)
            selection_ids, selection_scores = ids, scores
        else:
            # Fixed-window fallback
            ctx_block = build_context(self.eventlog, limit=5)

        # Check if graph context is actually present
        context_has_graph = "Graph Context:" in ctx_block
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

        # 3a. If assistant_reply is valid JSON with required string fields,
        #     record a deterministic, normalized payload in meta. Do NOT change
        #     the assistant message content to preserve existing control lines
        #     (e.g., COMMIT:/CLOSE:) and downstream behavior.
        structured_payload: Optional[str] = None
        try:
            parsed = json.loads(assistant_reply)
            if (
                isinstance(parsed, dict)
                and all(
                    k in parsed for k in ("intent", "outcome", "next", "self_model")
                )
                and all(
                    isinstance(parsed[k], str)
                    for k in ("intent", "outcome", "next", "self_model")
                )
            ):
                structured_payload = json.dumps(
                    parsed, sort_keys=True, separators=(",", ":")
                )
        except (TypeError, json.JSONDecodeError):
            structured_payload = None

        # 4. Log assistant message (content preserved; optional structured meta)
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
        # If vector retrieval, append embedding for assistant message (idempotent)
        if retrieval_cfg and retrieval_cfg.get("strategy") == "vector":
            model = str(retrieval_cfg.get("model", "hash64"))
            dims = int(retrieval_cfg.get("dims", 64))
            ensure_embedding_for_event(
                events=self.eventlog.read_all(),
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
            import json as _json2

            sel_content = _json2.dumps(
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
        synthesize_reflection(self.eventlog)
        maybe_append_summary(self.eventlog)

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
                import json as _json_claim

                claim_content = f"CLAIM:{claim.type}={_json_claim.dumps(claim.data, sort_keys=True, separators=(',', ':'))}"
                self.eventlog.append(
                    kind="claim",
                    content=claim_content,
                    meta={"claim_type": claim.type, "validated": True},
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

        if self.exec_router is not None:
            self.exec_router.tick()

        return decision
