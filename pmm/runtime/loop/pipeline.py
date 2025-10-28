"""Pipeline handlers (Stage 4 scaffolding).

Centralizes small, pure-ish stage handlers to make the loop slimmer and more
testable. For Stage 4 kick-off, we extract autonomy directive emission behind a
clear function, preserving behavior and payloads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pmm.directives.detector import extract as _extract_directives
from pmm.runtime import embeddings as _emb
from pmm.runtime.insight_scorer import COMPOSITE_THRESHOLD, score_insight
from pmm.runtime.llm_trait_adjuster import apply_llm_trait_adjustments
from pmm.runtime.loop import io as _io
from pmm.runtime.recall import suggest_recall
from pmm.runtime.validators import (
    DECISION_PROBE_PROMPT,
    GATE_CHECK_PROMPT,
    sanitize_language,
    validate_decision_probe,
    validate_gate_check,
)
from pmm.storage.projection import build_identity


def emit_autonomy_directives(
    eventlog, text: str, *, source: str, origin_eid: int
) -> None:
    """Extract autonomy directives from text and append events.

    Behavior is identical to the legacy inline implementation in the loop:
    - Uses the same detector `_extract_directives`
    - Emits `autonomy_directive` events via IO shim
    - Never raises to callers; failures are swallowed
    """
    try:
        for d in _extract_directives(text, source=source, origin_eid=int(origin_eid)):
            _io.append_autonomy_directive(
                eventlog,
                content=str(d.content),
                source=str(d.source),
                origin_eid=d.origin_eid,
            )
    except Exception:
        # Do not disrupt caller paths on directive extraction errors
        pass


__all__ = ["emit_autonomy_directives"]


def build_context_block(
    eventlog,
    snapshot,
    memegraph,
    *,
    max_commitment_chars: int,
    max_reflection_chars: int,
    diagnostics: dict | None = None,
) -> str:
    """Wrapper around build_context_from_ledger with fixed knobs.

    Mirrors the legacy call sites in handle_user and handle_user_stream.

    Performance optimization: Pass snapshot=None to enable read_tail optimization.
    The context_builder will use read_tail(1000) instead of snapshot.events (read_all),
    providing 50-100× speedup on large databases (100K+ events).
    The snapshot parameter is still passed to the caller for cached projections.
    """
    from pathlib import Path

    from pmm.runtime.context_builder import build_context_from_ledger

    context_block = build_context_from_ledger(
        eventlog,
        n_reflections=3,
        snapshot=None,  # Let context_builder use read_tail optimization
        memegraph=memegraph,
        max_commitment_chars=max_commitment_chars,
        max_reflection_chars=max_reflection_chars,
        compact_mode=False,
        include_metrics=False,
        include_commitments=True,  # Always include commitments for visibility
        include_reflections=False,
        diagnostics=diagnostics,
    )

    # DEBUG: Log context to file for inspection
    try:
        log_dir = Path(".logs")
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / "context_preview.txt"
        log_path.write_text(context_block, encoding="utf-8")
    except Exception:
        pass  # Don't fail if logging fails

    return context_block


def post_process_reply(eventlog, bridge, reply: str) -> tuple[str, int]:
    """Apply trait adjustments and sanitize the reply.

    Returns (sanitized_reply, applied_count). Exceptions are swallowed to keep
    behavior consistent with legacy code paths.
    """
    applied_count = 0
    try:
        applied_events = apply_llm_trait_adjustments(eventlog, reply)
        applied_count = len(applied_events) if applied_events else 0
    except Exception:
        pass

    try:
        # Use current adopted name for sanitizer
        adopted_name = build_identity(eventlog.read_all()).get("name")
        reply = bridge.sanitize(
            reply, family=bridge.model_family, adopted_name=adopted_name
        )
    except Exception:
        pass

    return reply, applied_count


__all__.extend(["build_context_block", "post_process_reply"])


def assemble_messages(
    *,
    context_block: str,
    ontology_msg: str,
    user_text: str,
    ontology_first: bool,
) -> list[dict[str, str]]:
    """Assemble base messages with deterministic ordering.

    - If `ontology_first` is True (streaming path), order is: ontology, context, user
    - Otherwise (non-streaming path), order is: context, ontology, user
    """
    if ontology_first:
        return [
            {"role": "system", "content": ontology_msg},
            {"role": "system", "content": context_block},
            {"role": "user", "content": user_text},
        ]
    else:
        return [
            {"role": "system", "content": context_block},
            {"role": "system", "content": ontology_msg},
            {"role": "user", "content": user_text},
        ]


__all__.append("assemble_messages")


def persist_reply_with_embedding(
    runtime,
    reply: str,
    *,
    meta: dict,
    raw_reply_for_telemetry: str | None = None,
    skip_embedding: bool = False,
) -> int | None:
    """Append response event and ensure an embedding_indexed is present.

    - Appends response with provided meta
    - Emits n-gram repeat telemetry using the raw (pre-scrub) reply if provided
    - Appends embedding_indexed for the response id; on failure, records skip
    - Idempotency check: if no embedding_indexed exists for the response in the
      recent tail, append a fallback digest entry
    """
    eventlog = runtime.eventlog
    rid = _io.append_response(eventlog, reply, meta=meta)

    # Telemetry on raw reply (pre-filter) if available
    try:
        runtime._maybe_emit_ngram_repeat_report(
            raw_reply_for_telemetry or reply, int(rid) if rid else 0
        )
    except Exception:
        pass

    if not skip_embedding and rid is not None:
        try:
            vec = _emb.compute_embedding(reply)
            if isinstance(vec, list) and vec:
                _io.append_embedding_indexed(
                    eventlog, eid=int(rid), digest=_emb.digest_vector(vec)
                )
            else:
                runtime._record_embedding_skip(int(rid))
        except Exception as exc:  # keep legacy resilience + telemetry
            try:
                runtime._last_embedding_exception = exc
            except Exception:
                pass
            runtime._record_embedding_skip(int(rid))

        # Final guard: ensure an embedding exists in recent tail; if not, add fallback
        try:
            recent_emb = eventlog.read_tail(limit=5)
        except Exception:
            recent_emb = []
        if not any(
            ev.get("kind") == "embedding_indexed"
            and (ev.get("meta") or {}).get("eid") == int(rid)
            for ev in recent_emb
        ):
            try:
                vec = _emb.compute_embedding(reply)
                digest = (
                    _emb.digest_vector(vec)
                    if isinstance(vec, list) and vec
                    else "fallback"
                )
                _io.append_embedding_indexed(eventlog, eid=int(rid), digest=digest)
            except Exception as exc:
                try:
                    runtime._last_embedding_exception = exc
                except Exception:
                    pass
                runtime._record_embedding_skip(int(rid))

    return rid


__all__.append("persist_reply_with_embedding")


def reply_post_llm(
    runtime,
    reply: str,
    *,
    user_text: str | None = None,
    meta: dict,
    raw_reply_for_telemetry: str | None = None,
    skip_embedding: bool = False,
    apply_validators: bool = True,
    run_commitment_hooks: bool = False,
    emit_directives: bool = False,
    directive_source: str | None = None,
) -> tuple[str, int | None]:
    """End-of-turn sequence orchestrator (behavior preserving).

    Order:
    1) Optionally apply operator validators to the reply (decision probe/gate check)
    2) Persist reply + ensure embedding (idempotent)
    3) Score insights and emit `insight_scored` (if applicable)
    4) Optionally run commitment/evidence hooks (must occur before directives)
    5) Optionally emit autonomy directives (only when requested)

    Returns: (possibly modified reply, response_event_id)
    """
    # 1) Validators
    if apply_validators and user_text is not None:
        try:
            reply = apply_operator_validators(runtime.eventlog, reply, user_text)
        except Exception:
            pass

    # 2) Persist reply + embedding
    meta = dict(meta or {})

    def _sanitize_claims(raw_claims) -> list[int]:
        normalized: list[int] = []
        for item in raw_claims or []:
            try:
                value = int(item)
            except (TypeError, ValueError):
                continue
            if value > 0:
                normalized.append(value)
        if not normalized:
            return []
        return sorted(dict.fromkeys(normalized))

    try:
        pending_claims = (
            runtime.consume_pending_claimed_reflection_ids()
            if hasattr(runtime, "consume_pending_claimed_reflection_ids")
            else None
        )
    except Exception:
        pending_claims = None

    sanitized_meta_claims = _sanitize_claims(meta.get("claimed_reflection_ids"))
    sanitized_pending_claims = _sanitize_claims(pending_claims)

    if sanitized_meta_claims and sanitized_pending_claims:
        merged = sorted(dict.fromkeys(sanitized_meta_claims + sanitized_pending_claims))
        meta["claimed_reflection_ids"] = merged
    elif sanitized_pending_claims:
        meta["claimed_reflection_ids"] = sanitized_pending_claims
    elif sanitized_meta_claims:
        meta["claimed_reflection_ids"] = sanitized_meta_claims
    else:
        meta.pop("claimed_reflection_ids", None)

    rid = persist_reply_with_embedding(
        runtime,
        reply,
        meta=meta,
        raw_reply_for_telemetry=raw_reply_for_telemetry,
        skip_embedding=skip_embedding,
    )

    # 3) Insight scoring emission (after response append)
    try:
        _ = score_insights_and_emit(runtime.eventlog, reply, int(rid) if rid else None)
    except Exception:
        pass

    # 4) Optional commitment/evidence hooks
    if run_commitment_hooks and rid is not None:
        try:
            run_commitment_evidence_hooks(runtime, reply, response_eid=int(rid))
        except Exception:
            pass

    # 5) Optional directive emission
    if emit_directives and directive_source and rid is not None:
        try:
            emit_autonomy_directives(
                runtime.eventlog, reply, source=directive_source, origin_eid=int(rid)
            )
        except Exception:
            pass

    return reply, rid


__all__.append("reply_post_llm")


def run_commitment_evidence_hooks(
    runtime, reply: str, *, response_eid: int | None
) -> None:
    """Run commitment/evidence hooks after a reply is persisted.

    Mirrors legacy behavior:
    - Close reflection-driven commitments satisfied by reply
    - Process text-only evidence for open commitments
    - Extract commitments from text using runtime helper
    """
    try:
        runtime.tracker.close_reflection_on_next(reply)
    except Exception:
        pass
    try:
        runtime.tracker.process_evidence(reply)
    except Exception:
        pass
    try:
        runtime._extract_commitments_from_text(
            reply, source_event_id=int(response_eid or 0), speaker="assistant"
        )
    except Exception:
        pass


__all__.append("run_commitment_evidence_hooks")


def finalize_telemetry(eventlog, profiler, request_log) -> None:
    """Export performance trace and log request cache stats.

    This mirrors the legacy post-reply telemetry and keeps behavior unchanged.
    """
    try:
        _io.export_performance_trace(eventlog, profiler=profiler)
        cache_stats = request_log.get_cache_stats()
        logging.getLogger(__name__).debug(
            "Request cache: %s hits, %s misses, hit_rate=%.1f%%",
            cache_stats.get("hits", 0),
            cache_stats.get("misses", 0),
            100.0 * float(cache_stats.get("hit_rate", 0.0)),
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "Failed to export performance profile", exc_info=True
        )


__all__.append("finalize_telemetry")


def augment_messages_with_state_and_gates(
    runtime,
    msgs: list[dict[str, str]],
    user_text: str,
    intents: dict[str, float] | None,
) -> list[dict[str, str]]:
    """Augment base messages with state summary and gate prompts.

    - If `intents` present, add a state summary system message (best-effort)
    - Inject decision probe and/or gate-check prompts deterministically
    - Returns a new messages list (original unmodified)
    """
    out = list(msgs)

    # State summary injection
    if intents:
        try:
            state_summary = runtime.describe_state()
            summary_text = runtime._format_state_summary(state_summary, intents)
            if summary_text:
                out.append({"role": "system", "content": summary_text})
        except Exception:
            # Preserve legacy silent failure
            pass

    # Strict-operator prompts
    try:
        lowq = (user_text or "").lower()
        wants_decision_probe = bool(
            ("use" in lowq and "2" in lowq and ("memgraph" in lowq or "graph" in lowq))
            or "observation (specific" in lowq
        )
        wants_gate_check = "evaluate only these gates" in lowq
        if wants_decision_probe:
            out.append({"role": "system", "content": DECISION_PROBE_PROMPT})
        if wants_gate_check:
            out.append({"role": "system", "content": GATE_CHECK_PROMPT})
    except Exception:
        pass

    return out


__all__.append("augment_messages_with_state_and_gates")


def apply_operator_validators(eventlog, reply: str, user_text: str) -> str:
    """Apply decision-probe and gate-check validators to a reply.

    Returns possibly modified reply. Emits a validator_failed breadcrumb on
    failure, mirroring legacy behavior.
    """
    try:
        lowq = (user_text or "").lower()
        dec_probe = bool(
            ("use" in lowq and "2" in lowq and ("memgraph" in lowq or "graph" in lowq))
            or "observation (specific" in lowq
        )
        gate_chk = "evaluate only these gates" in lowq
        if dec_probe or gate_chk:
            cleaned = sanitize_language(reply)
            valid = True
            reason = ""
            validator_name = ""
            if dec_probe:
                validator_name = "decision_probe"
                valid, reason = validate_decision_probe(cleaned, eventlog)
            elif gate_chk:
                validator_name = "gate_check"
                valid, reason = validate_gate_check(cleaned, eventlog)
            if not valid:
                reply2 = (
                    reason
                    if reason.startswith("INSUFFICIENT EVIDENCE")
                    else (
                        "INSUFFICIENT EVIDENCE — need valid ledger IDs or concrete "
                        "observable. Provide 2 real e#### and restate."
                    )
                )
                try:
                    _io.append_validator_failed(
                        eventlog, validator=validator_name, reason=reason
                    )
                except Exception:
                    pass
                return reply2
            else:
                return cleaned
        return reply
    except Exception:
        return reply


__all__.append("apply_operator_validators")


def score_insights_and_emit(eventlog, reply: str, response_eid: int | None) -> dict:
    """Compute insight scores and emit insight_scored if composite is present."""
    try:
        scores = score_insight(reply)
    except Exception:
        return {}
    if scores.get("composite"):
        try:
            _io.append_insight_scored(
                eventlog,
                scores=scores,
                response_eid=int(response_eid) if response_eid else None,
                passes=bool(scores.get("composite", 0.0) >= COMPOSITE_THRESHOLD),
            )
        except Exception:
            pass
    return scores


__all__.append("score_insights_and_emit")


def enforce_constraints(
    runtime, msgs: list[dict], reply: str, user_text: str, identity_name: str | None
) -> str:
    """Apply deterministic constraint checks and perform a one-shot correction.

    Mirrors inline logic in the loop: checks desired word counts, comma bans,
    bullet formatting, and name preambles. If violations exist, crafts a
    correction system message and generates a corrected reply with temperature 0.
    """
    try:
        # Import helpers from loop (executed facade)
        from pmm.runtime.loop import (
            _count_words,
            _forbids_preamble,
            _wants_bullets,
            _wants_exact_words,
            _wants_no_commas,
        )

        violations: list[str] = []
        n_exact = _wants_exact_words(user_text)
        if n_exact is not None and _count_words(reply) != int(n_exact):
            violations.append(f"Return exactly {int(n_exact)} words")
        if _wants_no_commas(user_text) and ("," in (reply or "")):
            violations.append("No commas allowed")
        if _wants_bullets(user_text) and not (
            reply.strip().startswith("One:") and "\n" in reply and "Two:" in reply
        ):
            violations.append("Start with 'One:' then 'Two:'; each five words")
        if _forbids_preamble(user_text, identity_name or ""):
            reply_stripped = (reply or "").lstrip()
            name = str(identity_name or "")
            if reply_stripped.lower().startswith("i am") or (
                name and reply_stripped.startswith(name)
            ):
                violations.append("Do not preface with your name")
        if violations:
            correction_msg = {
                "role": "system",
                "content": (
                    "Fix the previous answer. "
                    + "; ".join(violations)
                    + ". Output only the corrected text."
                ),
            }
            msgs2 = list(msgs) + [correction_msg]
            styled2 = runtime.bridge.format_messages(msgs2, intent="chat")
            reply2 = runtime._generate_reply(
                styled2, temperature=0.0, max_tokens=1536, allow_continuation=False
            )
            if reply2:
                return reply2
        return reply
    except Exception:
        return reply


__all__.append("enforce_constraints")


def persist_user_with_embedding(
    eventlog,
    user_text: str,
    meta: dict,
    *,
    record_skip: Callable[[int], None] | None = None,
) -> int | None:
    """Append a user event and ensure an embedding_indexed exists (idempotent).

    - Appends user event with provided meta
    - Computes embedding; appends embedding_indexed if available
    - On failure or empty vector, records an embedding_skipped via record_skip
    - Final guard: if no embedding_indexed exists for this user eid in recent
      tail, append a fallback digest entry
    """
    try:
        uid = _io.append_user(eventlog, user_text, meta=meta)
    except Exception:
        return None
    if uid is None:
        return None
    eid_int = int(uid)
    try:
        vec = _emb.compute_embedding(user_text)
        if isinstance(vec, list) and vec:
            _io.append_embedding_indexed(
                eventlog, eid=eid_int, digest=_emb.digest_vector(vec)
            )
        else:
            if record_skip:
                try:
                    record_skip(eid_int)
                except Exception:
                    pass
    except Exception:
        if record_skip:
            try:
                record_skip(eid_int)
            except Exception:
                pass
    # Ensure an embedding exists in tail; if missing, append fallback digest
    try:
        recent = eventlog.read_tail(limit=10)
    except Exception:
        recent = []
    if not any(
        ev.get("kind") == "embedding_indexed"
        and (ev.get("meta") or {}).get("eid") == eid_int
        for ev in recent
    ):
        try:
            vec = _emb.compute_embedding(user_text)
            digest = (
                _emb.digest_vector(vec) if isinstance(vec, list) and vec else "fallback"
            )
            _io.append_embedding_indexed(eventlog, eid=eid_int, digest=digest)
        except Exception:
            if record_skip:
                try:
                    record_skip(eid_int)
                except Exception:
                    pass
    return uid


__all__.append("persist_user_with_embedding")


def capture_knowledge_asserts(eventlog, user_text: str) -> list[str]:
    """Capture short declarative knowledge lines and append them as assertions.

    Returns the list of up to 5 captured assertions (used for same-turn context).
    """
    try:
        ut2 = str(user_text or "")
        if "```" in ut2:
            return []
        assertions: list[str] = []
        for raw in ut2.splitlines():
            line = str(raw or "").strip()
            if not line:
                continue
            for prefix in ["-", "*", "•"]:
                if line.startswith(prefix):
                    line = line[len(prefix) :].strip()
                    break
            if line and line[0].isdigit():
                parts = line.split(".", 1)
                if len(parts) == 2 and parts[0].isdigit():
                    line = parts[1].strip()
            if (
                len(line) <= 120
                and any(c.isalnum() for c in line)
                and ("?" not in line)
                and ("!" not in line)
            ):
                assertions.append(line if line.endswith(".") else (line + "."))
        captured = list(assertions[:5])
        for a in captured:
            try:
                _io.append_knowledge_assert(eventlog, content=a, source="handle_user")
            except Exception:
                pass
        return captured
    except Exception:
        return []


__all__.append("capture_knowledge_asserts")


def suggest_and_emit_recall(
    eventlog,
    evs_before: list[dict],
    reply: str,
    *,
    seeds: list[int] | None = None,
) -> list[dict]:
    """Compute recall suggestions from the provided window and emit event.

    Mirrors the loop logic: filters to valid, prior IDs, caps snippet length, and
    appends a single recall_suggest event if any suggestions remain.
    """
    try:
        suggestions = suggest_recall(
            evs_before, reply, max_items=3, semantic_seeds=seeds
        )
    except Exception:
        suggestions = []
    if not suggestions:
        return []
    latest_id_pre = int(evs_before[-1].get("id") or 0) if evs_before else 0
    seen: set[int] = set()
    clean: list[dict] = []
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
        try:
            _io.append_recall_suggest(eventlog, suggestions=clean)
        except Exception:
            pass
    return clean


__all__.append("suggest_and_emit_recall")
