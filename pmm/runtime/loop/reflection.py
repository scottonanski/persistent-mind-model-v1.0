"""Reflection emission and gating logic (Stage 4 extraction).

Extracts emit_reflection() and maybe_reflect() from the monolithic loop.py to reduce
its size. All behavior preserved exactly as-is per CONTRIBUTING.md.
"""

from __future__ import annotations

import logging
import time as _time
from collections.abc import Callable

from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.introspection import run_audit
from pmm.runtime.loop import io as _io
from pmm.runtime.loop import pipeline as _pipeline
from pmm.runtime.metrics import get_or_compute_ias_gas
from pmm.runtime.profiler import get_global_profiler
from pmm.runtime.stage_tracker import StageTracker, stage_str_to_level
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model

logger = logging.getLogger(__name__)

profiler = get_global_profiler()


def emit_reflection(
    eventlog: EventLog,
    content: str = "",
    *,
    events: list[dict] | None = None,
    forced: bool = False,
    stage_override: str | None = None,
    style_override_arm: str | None = None,
    forced_reason: str | None = None,
    force_open_commitment: bool = False,
    open_autonomy_tick: int | None = None,
    commitment_protect_until_tick: int | None = None,
    llm_generate: Callable | None = None,
) -> int | None:
    from pmm.runtime.loop import (
        _append_reflection_check,
        _last_policy_params,
        generate_system_status_reflection,
    )
    from pmm.runtime.loop import assessment as _assessment

    _maybe_emit_meta_reflection = _assessment.maybe_emit_meta_reflection
    _maybe_emit_self_assessment = _assessment.maybe_emit_self_assessment
    _apply_self_assessment_policies = _assessment.apply_self_assessment_policies
    _maybe_rotate_assessment_formula = _assessment.maybe_rotate_assessment_formula

    # Compute telemetry first so we can embed in the reflection meta
    # Performance: Use passed events if available, otherwise use routed context
    # Reflections benefit from full history access via semantic routing
    if events is None:
        try:
            from pmm.runtime.event_router import ContextQuery
            from pmm.runtime.routed_integration import (
                create_routed_infrastructure,
                is_routed_context_enabled,
            )

            if is_routed_context_enabled():
                # Use routed context for full history access
                event_index, event_router, identity_resolver = (
                    create_routed_infrastructure(eventlog)
                )

                # Route for reflection-relevant events
                reflection_query = ContextQuery(
                    required_kinds=[
                        "reflection",
                        "autonomy_tick",
                        "metrics_update",
                        "trait_update",
                    ],
                    semantic_terms=[],
                    limit=100,  # Get sufficient context for metrics computation
                    recency_boost=0.8,  # Strong recency bias for current state
                )
                event_ids = event_router.route(reflection_query)
                events = eventlog.read_by_ids(event_ids, verify_hash=False)
            else:
                # Fallback to tail optimization
                events = eventlog.read_tail(limit=1000)
        except Exception:
            # Final fallback
            try:
                events = eventlog.read_tail(limit=1000)
            except (AttributeError, TypeError):
                events = eventlog.read_all()
    # Performance: Use cached metrics computation
    ias, gas = get_or_compute_ias_gas(eventlog)
    synth = None
    try:
        stage_str = stage_override
        _snap = None
        if stage_str is None:
            stage_str, _snap = StageTracker.infer_stage(events)
    except Exception:
        stage_str = None
    stage_level = stage_str_to_level(stage_str)

    trait_map: dict[str, float] = {}
    try:
        with profiler.measure("build_self_model"):
            model_snapshot = build_self_model(events, eventlog=eventlog)
        trait_map = dict((model_snapshot.get("identity") or {}).get("traits") or {})
    except Exception:
        trait_map = {}

    novelty_threshold: float | None = None
    try:
        _stage_last, cooldown_params = _last_policy_params(events, "cooldown")
        if isinstance(cooldown_params, dict) and "novelty_threshold" in cooldown_params:
            novelty_threshold = float(cooldown_params.get("novelty_threshold"))
    except Exception:
        novelty_threshold = None

    def _format_traits(traits: dict[str, float]) -> str:
        axis = [
            ("openness", "O"),
            ("conscientiousness", "C"),
            ("extraversion", "E"),
            ("agreeableness", "A"),
            ("neuroticism", "N"),
        ]
        parts: list[str] = []
        for key, label in axis:
            try:
                val = float(traits.get(key, "nan"))
                parts.append(f"{label}:{val:.2f}")
            except Exception:
                parts.append(f"{label}:n/a")
        return ", ".join(parts)

    trait_summary = _format_traits(trait_map)
    policy_summary = (
        f"cooldown.novelty_threshold={novelty_threshold:.2f}"
        if isinstance(novelty_threshold, float)
        else "cooldown.novelty_threshold=unset"
    )
    templates = {
        0: (
            "succinct",
            "Reflect on your current IAS/GAS metrics, open commitments, and "
            "trait deltas. **Describe observations only - do NOT use commitment "
            "phrases like 'I will' or 'plan to'.** Focus on analysis and insights. "
            "Propose one concrete system-level action (e.g., adjust novelty threshold, "
            "open/close a commitment). Avoid generic advice unrelated to PMM internals.",
        ),
        1: (
            "question",
            "Ask yourself 2 short questions about your ledger integrity and "
            "stage progression. **Avoid commitment language ('I will', 'I'll').** "
            "Answer with one actionable system improvement (e.g., update policy, "
            "compact scenes). Focus only on PMM internals, not general philosophy.",
        ),
        2: (
            "narrative",
            "Summarize recent changes in traits or commitments based on ledger "
            "events. **Use descriptive language, not commitment phrases.** "
            "Suggest one system adjustment (e.g., tighten cadence). Avoid non-PMM topics.",
        ),
        3: (
            "checklist",
            "Produce a 3-item checklist: (1) what IAS/GAS changed, (2) what "
            "policy needs adjustment, (3) one immediate system action. "
            "**State observations, not commitments.** Restrict to PMM internals.",
        ),
        4: (
            "analytical",
            "Provide an analytical reflection: observe your current stage and "
            "commitments → diagnose gaps in autonomy → propose one concrete "
            "intervention (e.g., ratchet trait, close low-priority tasks). "
            "**Describe what should happen, not what 'I will' do.** "
            "Exclude generic or external advice.",
        ),
    }
    tmpl_label, tmpl_instr = templates.get(int(stage_level), templates[0])
    # Apply explicit style override arm, if provided by the caller.
    style_source = "stage_default"
    try:
        if style_override_arm:
            import logging

            from pmm.runtime.reflection_bandit import ARM_TO_PROMPT_LABEL, ARMS

            logger = logging.getLogger(__name__)

            # Validate arm is known
            _arm_str = str(style_override_arm)
            if _arm_str not in ARMS:
                logger.debug(
                    "Unknown style_override_arm '%s', defaulting to succinct. Valid arms: %s",
                    _arm_str,
                    ARMS,
                )
                _arm_str = "succinct"

            _lbl = ARM_TO_PROMPT_LABEL.get(_arm_str)
            if _lbl is not None:
                for _, (lab, instr) in templates.items():
                    if lab == _lbl:
                        tmpl_label, tmpl_instr = lab, instr
                        style_source = "policy_override"
                        break
    except Exception:
        pass
    telemetry_preamble = (
        f"System status: IAS={ias:.3f}, GAS={gas:.3f}, Stage={stage_str}. "
        f"Traits (OCEAN): {trait_summary}. Policy knobs: {policy_summary}."
    )
    style_guidance = f"\n\nStyle: {tmpl_label}. Instructions: {tmpl_instr}"
    context_forced = (
        f"{telemetry_preamble} Reflecting on current state after forced reflection trigger."  # noqa: E501
        f"{style_guidance}"
    )
    context_regular = (
        f"{telemetry_preamble} Reflecting on current state and proposing next actions."  # noqa: E501
        f"{style_guidance}"
    )

    def _fallback_text(_: str) -> str:
        try:
            tick_local = int(eventlog.get_max_id())
        except Exception:
            tick_local = len(events) if isinstance(events, list) else None
        return generate_system_status_reflection(
            ias, gas, stage_str, eventlog, tick_local
        )

    def _call_generator(ctx: str) -> str:
        generator = llm_generate or _fallback_text
        try:
            produced = generator(ctx)
        except Exception:
            produced = _fallback_text(ctx)
        if not isinstance(produced, str):
            produced = str(produced or "")
        return produced

    provided_content = bool((content or "").strip())
    synth = None
    if not provided_content:
        with profiler.measure("llm_reflection_generation"):
            synth = _call_generator(context_forced if forced else context_regular)
        # Treat empty content as implicitly forced to ensure fallback is always recorded
        forced = True

    final_text = str(content) if provided_content else str(synth or "")
    if not final_text.strip():
        final_text = "(empty reflection)"

    # Build deterministic refs for reflection
    try:
        k_refs = 6
        evs_refs = events or []
        relevant_kinds = {"user", "response", "commitment_open", "evidence_candidate"}
        sel: list[int] = []
        for ev in reversed(evs_refs):
            if ev.get("kind") in relevant_kinds:
                try:
                    sel.append(int(ev.get("id") or 0))
                except Exception:
                    continue
                if len(sel) >= k_refs:
                    break
        sel = [i for i in reversed(sel) if i > 0]
    except Exception:
        sel = []
    # Preserve content verbatim (including trailing newlines) for reflection_check; avoid .strip()
    provided_content = bool((content or "").strip())
    raw_text_for_check = (
        final_text  # keep a copy BEFORE sanitization for reflection_check
    )
    # Sanitize reflection text deterministically before appending (storage only)
    try:
        from pmm.bridge.manager import sanitize as _san

        sanitized_text = _san(final_text, family=None)
    except Exception:
        sanitized_text = final_text

    # Acceptance gate (audit-only here). For forced reflections, run acceptance on the
    # final text and suppress the debug reject breadcrumb since we will emit the fallback.
    _events_for_gate = events
    _would_accept = True
    _reject_reason = "ok"
    _reject_meta: dict = {}
    try:
        from pmm.runtime.reflector import accept as _accept_reflection

        _would_accept, _reject_reason, _reject_meta = _accept_reflection(
            final_text or "(reflection)", _events_for_gate, None, None
        )
    except Exception:
        # If acceptor unavailable or crashes, default-allow
        _would_accept, _reject_reason, _reject_meta = True, "ok", {"quality_score": 0.8}
    # Apply quality checks to ALL reflections, including forced ones
    if not _would_accept:
        try:
            _io.append_reflection_rejected(
                eventlog,
                reason=_reject_reason,
                template=tmpl_label,
                scores=_reject_meta,
                accept_mode="audit",
                forced=forced,
            )
        except Exception:
            pass

        if (not provided_content) and _reject_reason in [
            "too_short",
            "empty_reflection",
            "policy_loop_detected",
        ]:
            try:
                try:
                    tick_id = int(eventlog.get_max_id()) + 1
                except Exception:
                    tick_id = len(events) + 1 if isinstance(events, list) else 1
                better_content = generate_system_status_reflection(
                    ias, gas, stage_str, eventlog, tick_id
                )
                sanitized_text = better_content
                _would_accept = True
                _reject_reason = "ok"
                _reject_meta = {"quality_score": 0.85, "len_chars": len(better_content)}
            except Exception as e:
                _io.append_name_attempt_user(
                    eventlog,
                    content="",
                    extra={
                        "fallback_error": str(e),
                        "original_reason": _reject_reason,
                    },
                )

        if not _would_accept and not forced:
            # Non-forced reflections that still fail after fallback are dropped
            return None
    if not sanitized_text.strip():
        sanitized_text = "(empty reflection)"
        raw_text_for_check = sanitized_text
    meta_payload = {
        "source": "reflector",
        "persona": "reflector",
        "telemetry": {
            "IAS": ias,
            "GAS": gas,
            "traits": trait_map,
            "policies": {
                "cooldown": {
                    "novelty_threshold": novelty_threshold,
                }
            },
        },
        "refs": sel,
        "stage_level": int(stage_level),
        "stage": stage_str,  # Add stage for context-aware analysis
        "prompt_template": tmpl_label,
        "style_source": style_source,  # Track whether style came from policy or default
    }
    # Force quality score in metadata for stage advancement
    quality_score = _reject_meta.get("quality_score", 0.8) if _reject_meta else 0.8
    # Ensure quality score is never 0.0 (which breaks stage advancement)
    if quality_score <= 0.0:
        quality_score = 0.8
    meta_payload["quality_score"] = round(quality_score, 3)
    if forced or forced_reason:
        meta_payload["forced"] = True
        if forced_reason:
            meta_payload["forced_reason"] = str(forced_reason)
    # Mirror reflection text into meta["text"] for downstream tooling compatibility
    # Always set meta["text"], even if empty, to ensure field consistency
    meta_payload["text"] = sanitized_text or ""
    rid = eventlog.append(
        kind="reflection",
        content=sanitized_text,
        meta=meta_payload,
    )

    # Manual stage advancement trigger after reflection
    try:
        from pmm.runtime.stage_manager import StageManager

        sm = StageManager(eventlog)
        current = sm.current_stage()
        if sm._criteria_met(current):
            advanced_stage = sm.check_and_advance()
            if advanced_stage:
                # Stage advancement occurred
                pass
    except Exception:
        # Don't let stage advancement errors break reflection emission
        pass

    # Paired reflection_check event after reflection append
    try:
        # Evaluate the original (unsanitized) text to correctly detect trailing blank lines
        _append_reflection_check(eventlog, int(rid), raw_text_for_check)
    except Exception:
        pass
    # NOTE: Commitment creation from reflections now happens in Runtime.reflect()
    # where action extraction occurs. This function only emits the reflection event.
    # Removed direct commitment_open creation to avoid using full reflection text.
    # Emit autonomy_directive events derived from the reflection content (final_text)
    try:
        _pipeline.emit_autonomy_directives(
            eventlog, final_text, source="reflection", origin_eid=int(rid)
        )
    except Exception:
        # Do not disrupt reflection path if directive extraction fails
        pass
    # Introspection audit after reflection: append audit_report events
    try:
        try:

            # Use routed context for audit - need broader event context
            evs_a = eventlog.read_tail(
                limit=1000
            )  # Keep tail for audit (performance critical)
        except (AttributeError, TypeError):
            evs_a = eventlog.read_all()
        with profiler.measure("run_audit"):
            audits = run_audit(evs_a, window=10)
        if audits:
            latest_id = int(evs_a[-1].get("id") or 0) if evs_a else 0
            for a in audits:
                m = dict((a.get("meta") or {}).items())
                targets = m.get("target_eids") or []
                clean_targets = sorted(
                    {int(t) for t in targets if int(t) > 0 and int(t) < latest_id}
                )
                m["target_eids"] = clean_targets
                content2 = str(a.get("content") or "")
                _io.append_audit_report(eventlog, content=content2, meta=m)
    except Exception:
        pass
    # Meta-reflection cadence: emit every N reflections with window metrics (idempotent)
    try:
        _maybe_emit_meta_reflection(eventlog, window=5)
        _maybe_emit_self_assessment(eventlog, window=10)
        _apply_self_assessment_policies(eventlog)
        _maybe_rotate_assessment_formula(eventlog)
    except Exception:
        pass
    return rid


def maybe_reflect(
    eventlog: EventLog,
    cooldown: ReflectionCooldown,
    *,
    events: list[dict] | None = None,
    now: float | None = None,
    novelty: float = 1.0,
    override_min_turns: int | None = None,
    override_min_seconds: int | None = None,
    arm_means: dict | None = None,
    guidance_items: list | None = None,
    commitment_protect_until: int | None = None,
    open_autonomy_tick: int | None = None,
    llm_generate: Callable | None = None,
    memegraph=None,
    style_override_arm: str | None = None,
) -> tuple[bool, str]:
    """Check cooldown gates with optional per-call overrides; emit reflection or breadcrumb debug event.

    Returns (did_reflect, reason). If skipped, reason is the gate name.

    Extracted from loop.py - preserves exact behavior.

    Args:
        eventlog: Event log instance
        cooldown: Reflection cooldown instance
        events: Optional pre-fetched events list (performance optimization)
        ... (other parameters)
        style_override_arm: Optional explicit arm name (e.g., 'succinct',
            'question_form') to enforce a stage/policy style without scanning
            ledger state inside this function.
    """
    # Import helpers from loop (executed facade)
    from pmm.runtime.loop import (
        _FORCEABLE_SKIP_REASONS,
        _FORCED_SKIP_THRESHOLD,
        _choose_arm_biased,
        _consecutive_reflect_skips,
        _resolve_reflection_policy_overrides,
    )

    # If cooldown is not provided, treat as disabled (no reflections attempted)
    if cooldown is None:
        return (False, "disabled")
    # Be resilient to different cooldown stub signatures in tests
    now_value = float(now) if now is not None else float(_time.time())

    # Performance: Use passed events if available, otherwise use routed context
    # Reflection decisions benefit from full history access via semantic routing
    if events is None:
        try:
            from pmm.runtime.event_router import ContextQuery
            from pmm.runtime.routed_integration import (
                create_routed_infrastructure,
                is_routed_context_enabled,
            )

            if is_routed_context_enabled():
                # Use routed context for reflection decisions
                event_index, event_router, identity_resolver = (
                    create_routed_infrastructure(eventlog)
                )

                # Route for reflection decision context
                decision_query = ContextQuery(
                    required_kinds=["reflection", "autonomy_tick", "commitment_open"],
                    semantic_terms=[],
                    limit=50,  # Sufficient for decision making
                    recency_boost=0.9,  # Strong recency bias for current state
                )
                event_ids = event_router.route(decision_query)
                events = eventlog.read_by_ids(event_ids, verify_hash=False)
            else:
                # Fallback to tail optimization
                events = eventlog.read_tail(limit=1000)
        except Exception:
            # Final fallback
            try:
                events = eventlog.read_tail(limit=1000)
            except (AttributeError, TypeError):
                events = eventlog.read_all()

    try:
        # Prefer explicit overrides; otherwise, apply policy override only if present.
        _events_for_gate = events
        pol_mt, pol_ms = _resolve_reflection_policy_overrides(_events_for_gate)
        use_mt = override_min_turns if override_min_turns is not None else pol_mt
        use_ms = override_min_seconds if override_min_seconds is not None else pol_ms
        ok, reason = cooldown.should_reflect(
            now=now_value,
            novelty=novelty,
            override_min_turns=use_mt,
            override_min_seconds=use_ms,
            events=_events_for_gate,
        )
    except TypeError:
        # Fallback: some stubs accept only (now, novelty)
        try:
            ok, reason = cooldown.should_reflect(
                now=now_value, novelty=novelty, events=events
            )
        except TypeError:
            # Final fallback: no-arg call
            ok, reason = cooldown.should_reflect()
    if not ok:
        threshold = float(
            getattr(
                cooldown,
                "last_effective_novelty_threshold",
                getattr(cooldown, "novelty_threshold", 0.0),
            )
        )
        turns_since = getattr(cooldown, "turns_since", None)
        seconds_since = max(0.0, now_value - float(getattr(cooldown, "last_ts", 0.0)))
        try:
            novelty_val = float(novelty)
        except Exception:
            novelty_val = 0.0
        logger.info(
            "Reflection skipped: reason=%s novelty=%.3f threshold=%.3f turns=%s seconds_since=%.1f",
            reason,
            novelty_val,
            threshold,
            turns_since,
            seconds_since,
        )
        _io.append_reflection_skipped(eventlog, reason=reason)
        if reason in _FORCEABLE_SKIP_REASONS:
            streak = _consecutive_reflect_skips(eventlog, reason)
            if streak >= _FORCED_SKIP_THRESHOLD:
                forced_reason = f"skip_streak:{reason}"
                rid_forced = emit_reflection(
                    eventlog,
                    forced=True,
                    forced_reason=forced_reason,
                    force_open_commitment=True,
                    open_autonomy_tick=open_autonomy_tick,
                    commitment_protect_until_tick=commitment_protect_until,
                    llm_generate=llm_generate,
                )
                try:
                    cooldown.reset()
                except Exception:
                    pass
                _io.append_name_attempt_user(
                    eventlog,
                    content="",
                    extra={
                        "forced_reflection": {
                            "skip_reason": reason,
                            "consecutive": streak,
                            "forced_reflection_id": int(rid_forced),
                            "mode": "forced_commitment_open",
                        }
                    },
                )
                return (True, f"forced_{reason}")
        return (False, reason)
    rid = emit_reflection(
        eventlog,
        events=events,
        forced=False,
        open_autonomy_tick=open_autonomy_tick,
        commitment_protect_until_tick=commitment_protect_until,
        llm_generate=llm_generate,
        style_override_arm=style_override_arm,
    )
    if rid is None:
        return (False, "rejected")
    cooldown.reset()
    if memegraph is not None:
        try:
            graph_policy_ids = memegraph.policy_updates_for_reflection(int(rid))
            if logger.isEnabledFor(logging.DEBUG):
                legacy_policy_ids = []
                for ev in events:
                    if ev.get("kind") != "policy_update":
                        continue
                    meta = ev.get("meta") or {}
                    src = meta.get("src_id") or meta.get("source_event_id")
                    try:
                        src_int = int(src)
                    except Exception:
                        continue
                    if src_int == int(rid):
                        try:
                            legacy_policy_ids.append(int(ev.get("id") or 0))
                        except Exception:
                            continue
                if set(legacy_policy_ids) != set(graph_policy_ids):
                    logger.debug(
                        "memegraph policy mismatch for reflection %s: legacy=%s graph=%s",
                        rid,
                        legacy_policy_ids,
                        graph_policy_ids,
                    )
        except Exception:
            logger.debug("memegraph policy lookup failed", exc_info=True)
    # Bandit integration: choose arm via context-aware selection with guidance bias
    try:
        from pmm.runtime.reflection_bandit import (
            ARMS,
            PROMPT_LABEL_TO_ARM,
        )
        from pmm.runtime.reflection_bandit import (
            choose_arm as _choose_arm_contextual,
        )
        from pmm.runtime.stage_tracker import StageTracker

        events_now_bt = events
        tick_no_bandit = 1 + sum(
            1 for ev in events_now_bt if ev.get("kind") == "autonomy_tick"
        )

        # Infer current stage for context-aware arm selection
        try:
            current_stage, _ = StageTracker.infer_stage(events_now_bt)
        except Exception:
            current_stage = None

        arm = None
        arm_source = "bandit"

        # Priority 1: Use guidance-biased selection if guidance available
        if isinstance(arm_means, dict) and isinstance(guidance_items, list):
            try:
                arm, _delta_b = _choose_arm_biased(arm_means, guidance_items)
                arm_source = "bandit_biased"
            except Exception:
                arm = None

        # Priority 2: Use context-aware epsilon-greedy selection
        if arm is None:
            try:
                arm, _tick = _choose_arm_contextual(events_now_bt, stage=current_stage)
                arm_source = "bandit_contextual" if current_stage else "bandit"
            except Exception:
                arm = None

        # Priority 3: Fall back to last reflection's template
        if arm is None:
            for ev in reversed(events_now_bt):
                if ev.get("kind") == "reflection" and int(ev.get("id") or 0) == int(
                    rid
                ):
                    arm = (ev.get("meta") or {}).get("prompt_template")
                    break
            arm = str(arm or "succinct")
            arm_source = "fallback"
        # Idempotency: emit at most once per tick (since last autonomy_tick)
        try:
            evs_now_bt2 = events
        except Exception:
            evs_now_bt2 = events_now_bt
        last_auto_id_bt2 = None
        for be2 in reversed(evs_now_bt2):
            if be2.get("kind") == "autonomy_tick":
                last_auto_id_bt2 = int(be2.get("id") or 0)
                break
        already_bt2 = False
        for be2 in reversed(evs_now_bt2):
            if (
                last_auto_id_bt2 is not None
                and int(be2.get("id") or 0) <= last_auto_id_bt2
            ):
                break
            if be2.get("kind") == "bandit_arm_chosen":
                already_bt2 = True
                break
        if not already_bt2:
            # Double-check with fresh events to prevent race conditions
            try:
                fresh_events = eventlog.read_tail(limit=1000)
                fresh_already_bt = False
                fresh_last_auto_id = None
                for be in reversed(fresh_events):
                    if be.get("kind") == "autonomy_tick":
                        fresh_last_auto_id = int(be.get("id") or 0)
                        break
                for be in reversed(fresh_events):
                    if (
                        fresh_last_auto_id is not None
                        and int(be.get("id") or 0) <= fresh_last_auto_id
                    ):
                        break
                    if be.get("kind") == "bandit_arm_chosen":
                        fresh_already_bt = True
                        break
                if fresh_already_bt:
                    # Bandit already emitted this tick, skip
                    return (True, "ok")
            except Exception:
                pass

            # Normalize arm label to bandit ARMS naming (question -> question_form)
            try:
                # Use explicit style_override_arm if provided, otherwise use computed arm
                if style_override_arm:
                    _arm_norm = str(style_override_arm)
                    arm_source = "policy"
                else:
                    _arm_norm = str(arm or "")
                    # Normalize template label to arm name
                    _arm_norm = PROMPT_LABEL_TO_ARM.get(_arm_norm, _arm_norm)

                # Validate arm is known, default to succinct if not
                if _arm_norm not in ARMS:
                    logger.debug(
                        "Unknown arm '%s' for bandit_arm_chosen, defaulting to succinct. Valid: %s",
                        _arm_norm,
                        ARMS,
                    )
                    _arm_norm = "succinct"
            except Exception:
                _arm_norm = str(arm or "succinct")

            # Include context metadata for future contextual bandit analysis
            _io.append_bandit_arm_chosen(
                eventlog,
                arm=_arm_norm,
                tick=int(tick_no_bandit),
                extra={
                    "stage": current_stage,
                    "source": arm_source,  # "policy" or "bandit"
                },
            )
    except Exception:
        pass
    return (True, "ok")


__all__ = ["emit_reflection", "maybe_reflect"]
