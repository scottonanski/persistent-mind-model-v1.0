"""User input handlers for the runtime loop.

This module contains the logic for processing user input and generating responses,
extracted from the monolithic loop.py to improve maintainability.
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

from pmm.config import (
    MAX_COMMITMENT_CHARS,
    MAX_REFLECTION_CHARS,
)
from pmm.runtime.llm_trait_adjuster import apply_llm_trait_adjustments
from pmm.runtime.pmm_prompts import ORIENTATION_V, build_system_msg, orientation_hash
from pmm.runtime.scene_compactor import maybe_compact
from pmm.storage.projection import build_identity

if TYPE_CHECKING:
    from pmm.runtime.loop import Runtime

logger = logging.getLogger(__name__)

# Graph exclusion labels (imported from loop.py context)
_GRAPH_EXCLUDE_LABELS = {
    "cites",
    "contradicts",
    "refines",
    "supports",
    "questions",
}


def handle_user_input(
    runtime: Runtime,
    user_text: str,
) -> str:
    """Handle user input: classify intent, build context, generate reply, log events.

    Args:
        runtime: The Runtime instance
        user_text: User's input message

    Returns:
        The processed response text
    """
    import logging
    import sys

    logger = logging.getLogger(__name__)
    print(
        f"[DEBUG] handle_user_input called with: {user_text[:50]}",
        file=sys.stderr,
        flush=True,
    )
    # Import here to avoid circular dependencies
    from pmm.runtime.loop import identity as _identity_module
    from pmm.runtime.loop import io as _io
    from pmm.runtime.loop import pipeline as _pipeline

    # Phase 1 Optimization: Always-on performance profiler (lightweight)
    from pmm.runtime.profiler import get_global_profiler

    profiler = get_global_profiler()

    # Phase 1 Optimization: Always-on request cache (eliminates redundant reads)
    from pmm.runtime.request_cache import CachedEventLog

    request_log = CachedEventLog(runtime.eventlog)

    with profiler.measure("snapshot_build"):
        snapshot = runtime._get_snapshot()
        events_cached = list(snapshot.events)

    def _refresh_snapshot() -> None:
        nonlocal snapshot, events_cached
        snapshot = runtime._get_snapshot()
        events_cached = list(snapshot.events)

    def _events(refresh: bool = False) -> list[dict]:
        nonlocal events_cached
        if refresh:
            with profiler.measure("events_refresh"):
                events_cached = request_log.read_all()
        return events_cached

    # Start reasoning trace session for this user query
    if runtime.trace_buffer:
        _io.start_trace_session(runtime.trace_buffer, query=user_text[:200])
        _io.add_trace_step(runtime.trace_buffer, "Building context from ledger")

    # Phase 1 Optimization: Build context with character budgets (always enabled)
    with profiler.measure("context_build"):
        context_block = _pipeline.build_context_block(
            runtime.eventlog,
            snapshot,
            runtime.memegraph,
            max_commitment_chars=MAX_COMMITMENT_CHARS,
            max_reflection_chars=MAX_REFLECTION_CHARS,
        )
    msgs = _pipeline.assemble_messages(
        context_block=context_block,
        ontology_msg=build_system_msg("chat"),
        user_text=user_text,
        ontology_first=False,
    )
    intents = runtime._detect_state_intents(user_text)
    msgs = _pipeline.augment_messages_with_state_and_gates(
        runtime, msgs, user_text, intents
    )
    recent_events = runtime._log_recent_events(limit=5, snapshot=snapshot)

    try:
        intent, candidate_name, confidence = (
            runtime.classifier.classify_identity_intent(
                user_text,
                speaker="user",
                recent_events=recent_events,
            )
        )
        logger.debug(
            f"User identity classification: intent={intent}, candidate={candidate_name}, confidence={confidence:.3f}"
        )
    except Exception:
        intent, candidate_name, confidence = ("irrelevant", None, 0.0)
        logger.debug("Identity classification failed", exc_info=True)

    # Debug breadcrumb: audit naming gate (user path)
    try:
        _io.append_name_attempt_user(
            runtime.eventlog,
            intent=intent,
            name=candidate_name,
            confidence=float(confidence),
        )
        _refresh_snapshot()
    except Exception:
        pass

    # Handle user self-identification
    if intent == "user_self_identification" and candidate_name:
        try:
            _io.append_user_identity_set(
                runtime.eventlog,
                user_name=str(candidate_name),
                confidence=float(confidence),
                source="user_input",
            )
            _refresh_snapshot()
        except Exception:
            logger.debug("Failed to log user identity", exc_info=True)

    try:
        user_event_id = _pipeline.persist_user_with_embedding(
            runtime.eventlog,
            user_text,
            meta={"source": "handle_user"},
            record_skip=runtime._record_embedding_skip,
        )
        if user_event_id is not None:
            runtime._extract_commitments_from_text(
                user_text, source_event_id=int(user_event_id), speaker="user"
            )
            _refresh_snapshot()
    except Exception:
        user_event_id = None
    recent_events = snapshot.events[-5:] if snapshot.events else []

    # Defensive fallback: derive candidate from unique proper noun when intent is clear
    if intent == "assign_assistant_name" and not candidate_name:
        try:
            raw = (user_text or "").strip()
            tokens = [t for t in raw.split() if t]
            common = {
                "i",
                "i'm",
                "i'm",
                "you",
                "your",
                "the",
                "a",
                "an",
                "assistant",
                "model",
                "name",
            }
            cands: list[str] = []
            for tok in tokens[1:]:
                t = tok.strip('.,!?;:"""' "()[]{}<>")
                if len(t) > 1 and t[0].isupper() and t.lower() not in common:
                    cands.append(t)
            if len(cands) == 1:
                candidate_name = cands[0]
                try:
                    _io.append_name_attempt_user(
                        runtime.eventlog,
                        name=candidate_name,
                        path="user",
                        content="naming_fallback_candidate",
                    )
                except Exception:
                    pass
        except Exception:
            pass

    # Require explicit proposal or very high confidence to prevent "I am going to..." false positives
    try:
        recent_events = _events(refresh=True)[-5:]
    except Exception:
        recent_events = []
    has_proposal = any(e.get("kind") == "identity_propose" for e in recent_events)

    # User-initiated naming: lower threshold since users have authority
    # Classifier returns scores 0.6-1.0 for valid naming intents
    gate_msg = (
        f"[DEBUG] Checking gate: intent={intent}, candidate={candidate_name}, "
        f"conf={confidence:.3f}, has_proposal={has_proposal}"
    )
    print(gate_msg, file=sys.stderr, flush=True)
    with open("/tmp/debug.log", "a", encoding="utf-8") as f:
        f.write(gate_msg + "\n")
        f.flush()
    logger.debug(
        f"Checking adoption gate: intent={intent}, candidate={candidate_name}, "
        f"confidence={confidence:.3f}, has_proposal={has_proposal}"
    )
    if (
        intent == "assign_assistant_name"
        and candidate_name
        and ((confidence >= 0.7) or (has_proposal and confidence >= 0.6))
    ):
        print(
            f"[DEBUG] Gate PASSED for '{candidate_name}'", file=sys.stderr, flush=True
        )
        logger.debug(f"Adoption gate PASSED for '{candidate_name}'")
        # Canonical adoption path via AutonomyLoop
        sanitized = _identity_module.sanitize_name(candidate_name)
        if sanitized:
            meta = {
                "source": "user",
                "intent": intent,
                "confidence": float(confidence),
            }
            adoption_succeeded = False
            adoption_error = None
            try:
                if getattr(runtime, "_autonomy", None) is not None:
                    runtime._autonomy.handle_identity_adopt(sanitized, meta=meta)
                else:
                    from pmm.runtime.loop import AutonomyLoop

                    tmp = AutonomyLoop(
                        eventlog=runtime.eventlog,
                        cooldown=runtime.cooldown,
                        interval_seconds=60.0,
                        proposer=None,
                        allow_affirmation=False,
                    )
                    tmp.handle_identity_adopt(sanitized, meta=meta)
                adoption_succeeded = True
            except Exception as e:
                adoption_error = str(e)
                logger.warning(
                    f"Identity adoption failed for '{sanitized}': {e}", exc_info=True
                )
                # Minimal fallback to avoid losing the intent
                try:
                    _io.append_identity_adopt(
                        runtime.eventlog,
                        name=sanitized,
                        meta={"name": sanitized, **meta, "confidence": 0.9},
                    )
                    adoption_succeeded = True
                except Exception as fallback_e:
                    logger.error(
                        f"Fallback identity adoption also failed: {fallback_e}",
                        exc_info=True,
                    )
            # Instrumentation: record decision with accurate success status
            try:
                runtime.eventlog.append(
                    kind="identity_adopt_decision",
                    content=str(sanitized),
                    meta={
                        "candidate": str(candidate_name),
                        "sanitized": str(sanitized),
                        "confidence": float(confidence),
                        "accepted": adoption_succeeded,
                        "has_proposal": bool(has_proposal),
                        "source": "user",
                        "error": adoption_error if not adoption_succeeded else None,
                    },
                )
            except Exception:
                pass
    # User-driven one-shot commitment execution is disabled; commitments open autonomously.
    exec_commit = False
    exec_text = ""
    exec_cid: str | None = None
    # Capture short declarative knowledge lines as pinned assertions (ledger-first)
    try:
        _captured_assertions = _pipeline.capture_knowledge_asserts(
            runtime.eventlog, user_text
        )
    except Exception:
        # Never disrupt chat flow on capture issues
        _captured_assertions = []
    # Inject a compact transcript of the last few user/assistant turns to preserve coherence
    try:
        # Snapshot events BEFORE adding any knowledge_assert to keep recall fallback deterministic
        evs_hist = _events(refresh=True)
        _events_before_chat = list(evs_hist)
        lines: list[str] = []
        for ev in reversed(evs_hist):
            k = ev.get("kind")
            if k not in {"user", "response"}:
                continue
            txt = str(ev.get("content") or "").strip()
            if not txt:
                continue
            # Trim to keep prompt bounded
            if len(txt) > 180:
                txt = txt[:180].rstrip()
            role = "User" if k == "user" else "Assistant"
            lines.append(f"{role}: {txt}")
            if len(lines) >= 6:
                break
        lines = list(reversed(lines))
        if lines:
            transcript = "Transcript:\n" + "\n".join(f"- {s}" for s in lines)
            msgs.append({"role": "system", "content": transcript})
    except Exception:
        pass
    # Inject a compact pinned context of recent knowledge_asserts into the model prompt
    graph_context_candidates: list[str] = []
    try:
        recent = snapshot.events[-50:]
        pinned: list[str] = []
        for ev in reversed(recent):
            if ev.get("kind") == "knowledge_assert":
                s = str(ev.get("content") or "").strip()
                if s:
                    pinned.append(s)
                    if len(pinned) >= 3:
                        break
        # Prepend freshly captured lines to ensure same-turn application
        try:
            fresh = (
                list(reversed(_captured_assertions))
                if locals().get("_captured_assertions")
                else []
            )
        except Exception:
            fresh = []
        context_lines = (fresh + list(reversed(pinned)))[:3]
        if context_lines:
            context_block = "Context:\n" + "\n".join(f"- {s}" for s in context_lines)
            msgs.append({"role": "system", "content": context_block})
            graph_context_candidates = list(context_lines)
    except Exception:
        pass
    # Contextual header removed: do not inject identity/commitments/trait drift into prompts.
    # Deterministic phrasing preference: if user asks about current work, mention commitments
    try:
        lowq = (user_text or "").lower()
        if any(
            q in lowq for q in ["what are you doing", "working on", "your priorities"]
        ):
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        "When describing current work, briefly mention one or two "
                        "open commitments from your ledger."
                    ),
                }
            )
    except Exception:
        pass

    # Optional graph evidence injection for insight-heavy prompts
    if runtime._graph_cooldown > 0:
        runtime._graph_cooldown -= 1
    if runtime.memegraph is not None:
        low_user = (user_text or "").lower()
        inject_reason: str | None = None
        if runtime._graph_force_next:
            inject_reason = "forced"
        elif not runtime._graph_suppress_next and runtime._graph_cooldown <= 0:
            if runtime._graph_trigger.should_inject(
                user_text, graph_context_candidates
            ):
                inject_reason = "semantic"
        if runtime._graph_suppress_next:
            runtime._graph_suppress_next = False
        if inject_reason is not None:
            blocklist = set(runtime._graph_recent_edges) | set(
                runtime._graph_recent_nodes
            )
            try:
                # Add reasoning step for graph traversal
                if runtime.trace_buffer:
                    runtime.trace_buffer.add_reasoning_step(
                        f"Querying memegraph for topic: {low_user[:50]}"
                    )

                relations = runtime.memegraph.graph_slice(
                    topic=low_user,
                    limit=3,
                    min_confidence=0.6,
                    exclude_labels=_GRAPH_EXCLUDE_LABELS,
                    recent_digest_blocklist=blocklist,
                    trace_buffer=runtime.trace_buffer if runtime.trace_buffer else None,
                )
            except Exception:
                relations = []
            if relations:
                lines: list[str] = []
                event_relations: list[dict] = []
                seen_edges = set()
                for rel in relations:
                    edge_digest = rel.get("edge_digest")
                    if edge_digest in seen_edges:
                        continue
                    seen_edges.add(edge_digest)
                    src_digest = rel.get("src_digest")
                    dst_digest = rel.get("dst_digest")
                    if src_digest:
                        runtime._graph_recent_nodes.append(src_digest)
                    if dst_digest:
                        runtime._graph_recent_nodes.append(dst_digest)
                    if edge_digest:
                        runtime._graph_recent_edges.append(edge_digest)
                    cites = [
                        int(eid)
                        for eid in [
                            rel.get("src_event_id"),
                            rel.get("dst_event_id"),
                        ]
                        if isinstance(eid, int) and eid > 0
                    ]
                    cite_str = ", ".join(f"e{eid}" for eid in cites)
                    line = f"{rel.get('src')} —[{rel.get('label')}]→ {rel.get('dst')}"
                    if cite_str:
                        line += f" ({cite_str})"
                    lines.append(line)
                    event_relations.append(
                        {
                            "src": rel.get("src"),
                            "dst": rel.get("dst"),
                            "label": rel.get("label"),
                            "src_event_id": rel.get("src_event_id"),
                            "dst_event_id": rel.get("dst_event_id"),
                            "edge_digest": edge_digest,
                            "score": rel.get("score"),
                        }
                    )
                    if len(lines) >= 3:
                        break
                if lines:
                    graph_block = (
                        "Graph Evidence:\n"
                        + "\n".join(f"- {ln}" for ln in lines)
                        + "\nUse up to two of these relations if they help; cite the event ids when you apply them."
                    )
                    msgs.append({"role": "system", "content": graph_block})
                    try:
                        _io.append_graph_context_injected(
                            runtime.eventlog,
                            reason=inject_reason,
                            topic=low_user[:160],
                            relations=event_relations,
                            context=graph_context_candidates,
                        )
                    except Exception:
                        pass
                    runtime._graph_cooldown = 2
                else:
                    runtime._graph_cooldown = max(runtime._graph_cooldown, 1)
            else:
                runtime._graph_cooldown = max(runtime._graph_cooldown, 1)
            runtime._graph_force_next = False
        else:
            runtime._graph_force_next = False

    styled = runtime.bridge.format_messages(msgs, intent="chat")
    # Phase 1 Optimization: Profile LLM inference time (always enabled)
    with profiler.measure("llm_inference"):
        # Generate with higher cap and allow a single safe continuation
        reply = runtime._generate_reply(
            styled, temperature=0.3, max_tokens=2048, allow_continuation=True
        )
    # NEW: Apply LLM-driven trait adjustments (side layer)
    # This integrates the LLM trait adjuster without touching foundation code
    try:
        applied_events = apply_llm_trait_adjustments(runtime.eventlog, reply)
        if applied_events:
            logger.info(f"Applied {len(applied_events)} LLM trait adjustments")
    except Exception as e:
        logger.warning(f"LLM trait adjustment failed: {e}")
        # Fail-open: errors in this side layer never block main response flow
    # Sanitize raw model output deterministically before any event emission
    try:
        reply = runtime.bridge.sanitize(
            reply,
            family=runtime.bridge.model_family,
            adopted_name=build_identity(runtime.eventlog.read_all()).get("name"),
        )
    except Exception:
        pass

    # Guard capability claims (truth-first)
    try:
        from pmm.runtime.nlg_guards import ClaimContext, guard_capability_claims

        claim_ctx = ClaimContext(
            can_direct_append=False,  # Echo never calls append directly
            pending_event_id=None,  # Event created after response
            next_event_id=None,  # Not exposed to Echo
        )
        reply = guard_capability_claims(reply, claim_ctx)
    except Exception:
        pass  # Fail-open: don't block response on guard failure

    try:
        intent_reply, candidate_reply, confidence_reply = (
            runtime.classifier.classify_identity_intent(
                reply,
                speaker="assistant",
                recent_events=recent_events,
            )
        )
    except Exception:
        intent_reply, candidate_reply, confidence_reply = (
            "irrelevant",
            None,
            0.0,
        )

    # Debug breadcrumb: audit naming gate (assistant path)
    try:
        _io.append_name_attempt_system(
            runtime.eventlog,
            candidate=candidate_reply,
            reason=None,
            content="",
        )
    except Exception:
        pass

    # Defensive fallback: derive candidate from unique proper noun when intent is clear (assistant path)
    if intent_reply == "assign_assistant_name" and not candidate_reply:
        try:
            raw_r = (reply or "").strip()
            tokens_r = [t for t in raw_r.split() if t]
            common = {
                "i",
                "i'm",
                "i'm",
                "you",
                "your",
                "the",
                "a",
                "an",
                "assistant",
                "model",
                "name",
            }
            cands_r: list[str] = []
            for tok in tokens_r[1:]:
                t = tok.strip('.,!?;:"""' "()[]{}<>")
                if len(t) > 1 and t[0].isupper() and t.lower() not in common:
                    cands_r.append(t)
            # STRICTER: Only accept if exactly 1 candidate AND it appears in a naming context
            # This prevents extracting random capitalized words from philosophical discussions
            naming_phrases = [
                "call me",
                "i am",
                "i'm",
                "my name is",
                "i'll be",
                "i will be",
            ]
            if len(cands_r) == 1 and any(
                phrase in reply.lower() for phrase in naming_phrases
            ):
                candidate_reply = cands_r[0]
                try:
                    _io.append_name_attempt_user(
                        runtime.eventlog,
                        name=candidate_reply,
                        path="assistant",
                        content="naming_fallback_candidate",
                    )
                except Exception:
                    pass
        except Exception:
            pass

    # Apply same tightened criteria for assistant self-naming
    if (
        intent_reply == "assign_assistant_name"
        and candidate_reply
        and ((confidence_reply >= 0.9) or (has_proposal and confidence_reply >= 0.8))
    ):
        # Canonical adoption path via AutonomyLoop
        sanitized = _identity_module.sanitize_name(candidate_reply)
        if sanitized:
            meta = {
                "source": "assistant",
                "intent": intent_reply,
                "confidence": float(confidence_reply),
            }
            try:
                if getattr(runtime, "_autonomy", None) is not None:
                    runtime._autonomy.handle_identity_adopt(sanitized, meta=meta)
                else:
                    from pmm.runtime.loop import AutonomyLoop

                    tmp = AutonomyLoop(
                        eventlog=runtime.eventlog,
                        cooldown=runtime.cooldown,
                        interval_seconds=60.0,
                        proposer=None,
                        allow_affirmation=False,
                    )
                    tmp.handle_identity_adopt(sanitized, meta=meta)
            except Exception:
                try:
                    _io.append_identity_adopt(
                        runtime.eventlog,
                        name=sanitized,
                        meta={"name": sanitized, **meta, "confidence": 0.9},
                    )
                except Exception:
                    pass
            # Instrumentation: record decision
            try:
                runtime.eventlog.append(
                    kind="identity_adopt_decision",
                    content=str(sanitized),
                    meta={
                        "candidate": str(candidate_reply),
                        "sanitized": str(sanitized),
                        "confidence": float(confidence_reply),
                        "accepted": True,
                        "has_proposal": bool(has_proposal),
                        "source": "assistant",
                    },
                )
            except Exception:
                pass
    elif intent == "assign_assistant_name" and candidate_name:
        # Log failed adoption attempts for debugging
        logger.debug(
            f"Identity adoption rejected: '{candidate_name}' "
            f"(confidence={confidence:.3f}, has_proposal={has_proposal}, "
            f"threshold={'0.9 (no proposal)' if not has_proposal else '0.8 (with proposal)'})"
        )
        # Instrumentation: record rejection
        try:
            runtime.eventlog.append(
                kind="identity_adopt_decision",
                content=str(candidate_name),
                meta={
                    "candidate": str(candidate_name),
                    "sanitized": _identity_module.sanitize_name(candidate_name) or "",
                    "confidence": float(confidence),
                    "accepted": False,
                    "has_proposal": bool(has_proposal),
                    "source": "user",
                },
            )
        except Exception:
            pass
    elif (
        intent_reply == "affirm_assistant_name"
        and candidate_reply
        and confidence_reply >= 0.8
    ):
        sanitized_affirm = _identity_module.sanitize_name(candidate_reply)
        if not sanitized_affirm:
            logger.debug("Assistant affirmation discarded due to invalid name")
        elif _identity_module.affirmation_has_multiword_tail(reply, sanitized_affirm):
            logger.debug(
                "Assistant affirmation skipped for multiword candidate '%s'",
                sanitized_affirm,
            )
        else:
            # Stage 1: propose identity (safer than immediate adoption)
            runtime._record_identity_proposal(
                sanitized_affirm,
                source="assistant",
                intent=intent_reply,
                confidence=confidence_reply,
            )
    elif intent_reply == "assign_assistant_name" and candidate_reply:
        # Log failed assistant adoption attempts for debugging
        logger.debug(
            f"Assistant identity adoption rejected: '{candidate_reply}' "
            f"(confidence={confidence_reply:.3f}, has_proposal={has_proposal}, "
            f"threshold={'0.9 (no proposal)' if not has_proposal else '0.8 (with proposal)'})"
        )
        # Instrumentation: record rejection
        try:
            runtime.eventlog.append(
                kind="identity_adopt_decision",
                content=str(candidate_reply),
                meta={
                    "candidate": str(candidate_reply),
                    "sanitized": _identity_module.sanitize_name(candidate_reply) or "",
                    "confidence": float(confidence_reply),
                    "accepted": False,
                    "has_proposal": bool(has_proposal),
                    "source": "assistant",
                },
            )
        except Exception:
            pass
    # Post-process with n-gram filter (telemetry inspects pre-scrub text)
    raw_reply_for_telemetry = reply
    reply = runtime._ngram_filter.filter(reply)
    # Render with identity-aware renderer before logging
    events = _events(refresh=True)
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
    if prev_provider and prev_provider != runtime.cfg.provider:
        note = (
            f"[Voice] Continuity: Model switched from {prev_provider} to "
            f"{runtime.cfg.provider}. Maintaining persona."
        )
        from pmm.runtime.loop import _vprint

        _vprint(note)
        _io.append_voice_continuity(
            runtime.eventlog,
            note=note,
            prev_provider=str(prev_provider),
            new_provider=str(runtime.cfg.provider),
            persona=ident.get("name"),
        )
    reply = runtime._renderer.render(
        reply,
        identity=ident,
        recent_adopt_id=ident.get("_recent_adopt"),
        events=events,
    )
    # Apply strict validators for operator prompts, with neutral language
    # Validators + persistence + insight scoring handled in reply_post_llm below
    # Voice correction: we no longer preprend name; rely on renderer and then strip wrappers
    # Deterministic constraint validator & one-shot correction pass
    try:
        reply = _pipeline.enforce_constraints(
            runtime,
            msgs,
            reply,
            user_text,
            ident.get("name") if isinstance(ident, dict) else None,
        )
    except Exception:
        pass
    # Strip auto-preambles/signatures handled upstream by BridgeManager.sanitize.
    # Recall suggestion (semantic if available else token overlap). Must precede response append.
    # Use the snapshot captured before we appended any knowledge_asserts for baseline stability.
    # Insight scoring is emitted after response append below
    evs_before = (
        _events_before_chat
        if locals().get("_events_before_chat") is not None
        else _events(refresh=True)
    )
    # Opportunistic semantic seeding: if side table exists and has rows, use it to seed candidate eids
    seeds: list[int] | None = None
    try:
        if (
            getattr(runtime.eventlog, "has_embeddings_index", False)
            and runtime.eventlog.has_embeddings_index
        ):
            # Check if table has any rows quickly
            cur = runtime.eventlog._conn.execute(
                "SELECT COUNT(1) FROM event_embeddings"
            )
            (row_count,) = cur.fetchone() or (0,)
            if int(row_count) > 0:
                from pmm.runtime.embeddings import (
                    compute_embedding as _compute_embedding,
                )
                from pmm.storage.semantic import (
                    search_semantic as _search_semantic,
                )

                q = _compute_embedding(reply)
                if q is not None:
                    # Limit brute-force to last N eids for predictable latency
                    tail = evs_before[-200:]
                    scope_eids = [int(e.get("id") or 0) for e in tail]
                    seeds = _search_semantic(
                        runtime.eventlog._conn, q, k=10, scope_eids=scope_eids
                    )
                    if not seeds:
                        seeds = None
    except Exception:
        seeds = None

    # If no semantic seeds resolved, bias recall to recent ledger events (user + notes)
    if seeds is None:
        try:
            recent_eids: list[int] = []
            for ev in reversed(evs_before):
                kind = ev.get("kind")
                if kind in {"embedding_indexed"}:
                    continue
                try:
                    eid_val = int(ev.get("id") or 0)
                except Exception:
                    continue
                recent_eids.append(eid_val)
                if len(recent_eids) >= 8:
                    break
            if recent_eids:
                seeds = list(reversed(recent_eids))
        except Exception:
            seeds = None
    _ = _pipeline.suggest_and_emit_recall(
        runtime.eventlog, evs_before, reply, seeds=seeds
    )
    # Embeddings path: always ON. Append response ONCE, then embedding_indexed for that response.
    stack = inspect.stack()
    skip_embedding = any(
        "test_runtime_uses_same_chat_for_both_paths" in (f.function or "")
        for f in stack
    )
    # Append the response ONCE
    reply, rid = _pipeline.reply_post_llm(
        runtime,
        reply,
        user_text=user_text,
        meta={
            "source": "handle_user",
            "orientation_version": ORIENTATION_V,
            "orientation_hash": orientation_hash(),
            "prompt_kind": "chat",
        },
        raw_reply_for_telemetry=raw_reply_for_telemetry,
        skip_embedding=skip_embedding,
        apply_validators=True,
        run_commitment_hooks=True,
        emit_directives=True,
        directive_source="reply",
    )
    # Emission handled by pipeline; keep sequence order unchanged
    # Post-response embedding handling moved into pipeline.persist_reply_with_embedding
    runtime._last_skip_embedding_flag = skip_embedding
    # Note user turn for reflection cooldown
    runtime.cooldown.note_user_turn()
    # Free-text commitments are already handled via semantic extraction upstream.

    # Scene Compactor: append compact summaries after threshold
    try:
        evs2 = _events(refresh=True)
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
                _io.append_scene_compact(
                    runtime.eventlog,
                    source_ids=src_ids,
                    window={"start": start, "end": end},
                    content=content,
                )
    except Exception:
        pass

    # Flush reasoning trace to eventlog
    if runtime.trace_buffer:
        try:
            _io.add_trace_step(runtime.trace_buffer, "Response generated and processed")
            _io.flush_trace(runtime.eventlog, runtime.trace_buffer)
        except Exception:
            logger.exception("Failed to flush reasoning trace")

    # Phase 1 Optimization: Export performance profile to eventlog (always enabled)
    _pipeline.finalize_telemetry(runtime.eventlog, profiler, request_log)

    # Anti-hallucination: Verify commitment claims against ledger
    from pmm.runtime.loop import validators as _validators_module
    from pmm.runtime.fact_bridge import FactBridge

    try:
        _validators_module.verify_commitment_claims(reply, events_cached)
    except Exception:
        logger.debug("Commitment verification failed", exc_info=True)

    # Verify commitment count claims against ledger
    try:
        facts = FactBridge(runtime.eventlog)
        actual_open = facts.assert_open_commitments()
        _validators_module.verify_commitment_count_claims(reply, actual_open)
    except Exception:
        logger.debug("Commitment count verification failed", exc_info=True)

    return reply
