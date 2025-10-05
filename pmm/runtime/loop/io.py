"""IO and metrics hooks for the runtime loop (Stage 2 extraction).

This module centralizes side-effecting operations related to tracing and
performance metrics. It provides thin, behavior-preserving wrappers that the
legacy loop delegates to. External event payloads and ordering remain
unchanged.
"""

from __future__ import annotations


def start_trace_session(trace_buffer, query: str) -> None:
    """Begin a reasoning trace session if a buffer is provided."""
    if trace_buffer is None:
        return
    trace_buffer.start_session(query=query)


def add_trace_step(trace_buffer, text: str) -> None:
    """Append a reasoning step if a buffer is provided."""
    if trace_buffer is None:
        return
    trace_buffer.add_reasoning_step(text)


def flush_trace(eventlog, trace_buffer) -> int | None:
    """Flush the reasoning trace to the eventlog and return the event id."""
    if trace_buffer is None:
        return None
    return trace_buffer.flush_to_eventlog(eventlog)


def export_performance_trace(eventlog, profiler=None) -> int | None:
    """Export the current performance profile to the eventlog.

    If no profiler is provided, the global profiler is used.
    """
    if profiler is None:
        from pmm.runtime.profiler import get_global_profiler

        profiler = get_global_profiler()
    return profiler.export_to_trace_event(eventlog)


__all__ = [
    "start_trace_session",
    "add_trace_step",
    "flush_trace",
    "export_performance_trace",
    "append_user",
    "append_response",
    "append_embedding_indexed",
    "append_scene_compact",
    "append_autonomy_directive",
    "append_ngram_repeat_report",
    "append_insight_scored",
    "append_validator_failed",
    "append_voice_continuity",
    "append_name_attempt_user",
    "append_name_attempt_system",
    "append_graph_context_injected",
    "append_knowledge_assert",
    "append_audit_report",
    "append_hallucination_detected",
    "append_recall_suggest",
    "append_embedding_skipped",
    "append_user_identity_set",
    "append_identity_propose",
    "append_reflection_discarded",
    "append_reflection_action",
    "append_reflection_quality",
    "append_reflection_check",
    "append_identity_adopt",
    "append_name_updated",
    "append_identity_checkpoint",
    "append_trait_update",
    "append_commitment_rebind",
    "append_reflection_forced",
    "append_metrics",
    "append_policy_update",
    "append_assessment_policy_update",
    "append_bandit_arm_chosen",
    "append_bandit_reward",
    "append_meta_reflection",
    "append_self_assessment",
    "append_reflection_rejected",
    "append_reflection_skipped",
]


def append_user(eventlog, content: str, meta: dict | None = None):
    """Append a `user` event with the given content and meta."""
    return eventlog.append(kind="user", content=content, meta=meta or {})


def append_response(eventlog, content: str, meta: dict | None = None):
    """Append a `response` event with the given content and meta."""
    return eventlog.append(kind="response", content=content, meta=meta or {})


def append_embedding_indexed(eventlog, *, eid: int, digest: str):
    """Append an `embedding_indexed` event for a given eid and digest."""
    return eventlog.append(
        kind="embedding_indexed",
        content="",
        meta={"eid": int(eid), "digest": str(digest)},
    )


def append_scene_compact(
    eventlog, *, source_ids: list[int], window: dict, content: str
):
    """Append a `scene_compact` event with validated payload."""
    # Defensive truncation and normalization to match existing behavior
    clean_ids = [int(i) for i in source_ids if int(i) > 0]
    clean_ids.sort()
    start = int(window.get("start") or (clean_ids[0] if clean_ids else 0))
    end = int(window.get("end") or (clean_ids[-1] if clean_ids else 0))
    if not clean_ids or start > end:
        return None
    return eventlog.append(
        kind="scene_compact",
        content=str(content)[:500],
        meta={
            "source_ids": clean_ids,
            "window": {"start": start, "end": end},
        },
    )


def append_autonomy_directive(eventlog, *, content: str, source: str, origin_eid: int):
    """Append an `autonomy_directive` event with a standard meta payload."""
    return eventlog.append(
        kind="autonomy_directive",
        content=str(content),
        meta={"source": str(source), "origin_eid": int(origin_eid)},
    )


def append_ngram_repeat_report(eventlog, *, meta: dict):
    """Append an `ngram_repeat_report` event.

    Expects a meta payload already validated by the caller. Content is the
    literal string "analysis" to match legacy behavior.
    """
    return eventlog.append(kind="ngram_repeat_report", content="analysis", meta=meta)


def append_insight_scored(
    eventlog, *, scores: dict, response_eid: int | None, passes: bool
):
    """Append an `insight_scored` event with standard meta fields."""
    return eventlog.append(
        kind="insight_scored",
        content="",
        meta={
            "scores": scores,
            "response_eid": int(response_eid) if response_eid is not None else None,
            "passes": bool(passes),
        },
    )


def append_validator_failed(eventlog, *, validator: str, reason: str):
    """Append a `validator_failed` breadcrumb with capped reason length."""
    return eventlog.append(
        kind="validator_failed",
        content="",
        meta={"validator": str(validator), "reason": str(reason)[:160]},
    )


def append_voice_continuity(
    eventlog, *, note: str, prev_provider: str, new_provider: str, persona: str | None
):
    """Append a `voice_continuity` event with providers and persona info."""
    return eventlog.append(
        kind="voice_continuity",
        content=str(note),
        meta={
            "from": str(prev_provider),
            "to": str(new_provider),
            "persona": persona,
        },
    )


def append_name_attempt_user(
    eventlog,
    *,
    intent: str | None = None,
    name: str | None = None,
    confidence: float | None = None,
    content: str = "",
    path: str | None = None,
    extra: dict | None = None,
):
    """Append NAME_ATTEMPT_USER breadcrumb with standard meta."""
    from pmm.config import NAME_ATTEMPT_USER as _NAU

    meta: dict = {}
    if intent is not None:
        meta["intent"] = intent
    if name is not None:
        meta["name"] = name
    if confidence is not None:
        meta["confidence"] = float(confidence)
    if path is not None:
        meta["path"] = path
    if extra:
        for k, v in extra.items():
            meta[k] = v
    return eventlog.append(kind=_NAU, content=str(content), meta=meta)


def append_name_attempt_system(
    eventlog,
    *,
    candidate: str | None = None,
    reason: str | None = None,
    content: str = "",
):
    """Append NAME_ATTEMPT_SYSTEM breadcrumb with standard meta."""
    from pmm.config import NAME_ATTEMPT_SYSTEM as _NAS

    meta: dict = {}
    if candidate is not None:
        meta["candidate"] = candidate
    if reason is not None:
        meta["reason"] = reason
    return eventlog.append(kind=_NAS, content=str(content), meta=meta)


def append_graph_context_injected(
    eventlog, *, reason: str, topic: str, relations: list, context: list
):
    """Append a graph_context_injected event with standard meta."""
    return eventlog.append(
        kind="graph_context_injected",
        content="",
        meta={
            "reason": str(reason),
            "topic": str(topic)[:160],
            "relations": relations,
            "context": context,
        },
    )


def append_knowledge_assert(eventlog, *, content: str, source: str = "handle_user"):
    """Append a knowledge_assert event from a deterministic source."""
    return eventlog.append(
        kind="knowledge_assert", content=str(content), meta={"source": source}
    )


def append_audit_report(eventlog, *, content: str, meta: dict):
    """Append an audit_report event with deterministic truncation (<=500 chars)."""
    return eventlog.append(
        kind="audit_report",
        content=str(content)[:500],
        meta=meta or {},
    )


def append_hallucination_detected(eventlog, *, fake_ids: list[int], correction: str):
    """Append a hallucination_detected event with standard meta fields."""
    return eventlog.append(
        kind="hallucination_detected",
        content=f"Fabricated event IDs: {list(fake_ids)}",
        meta={
            "fake_ids": list(fake_ids),
            "correction": str(correction),
        },
    )


def append_recall_suggest(eventlog, *, suggestions: list[dict]):
    """Append a recall_suggest event with provided suggestions list.

    Expects items shaped like {"eid": int, "snippet": str} (already validated upstream).
    """
    return eventlog.append(
        kind="recall_suggest", content="", meta={"suggestions": list(suggestions)}
    )


def append_embedding_skipped(eventlog, *, eid: int):
    """Append a debounced embedding_skipped event for the given eid.

    Checks a small tail window to avoid duplicate entries for the same eid.
    """
    try:
        tail = eventlog.read_tail(limit=20)
    except TypeError:
        tail = eventlog.read_tail(20)  # type: ignore[arg-type]
    except Exception:
        tail = []
    for ev in reversed(tail):
        if ev.get("kind") != "embedding_skipped":
            continue
        meta = ev.get("meta") or {}
        try:
            existing = int(meta.get("eid") or 0)
        except Exception:
            existing = 0
        if existing == int(eid):
            return None
    return eventlog.append(kind="embedding_skipped", content="", meta={"eid": int(eid)})


def append_user_identity_set(
    eventlog, *, user_name: str, confidence: float, source: str = "user_input"
):
    """Append a user_identity_set event with standard meta fields."""
    return eventlog.append(
        kind="user_identity_set",
        content=f"User identified as: {user_name}",
        meta={
            "user_name": str(user_name),
            "confidence": float(confidence),
            "source": str(source),
        },
    )


def append_identity_propose(
    eventlog, *, name: str, source: str, intent: str, confidence: float
):
    """Append an identity_propose event with standard meta fields."""
    return eventlog.append(
        kind="identity_propose",
        content=str(name),
        meta={
            "source": str(source),
            "intent": str(intent),
            "confidence": float(confidence),
        },
    )


def append_reflection_discarded(
    eventlog, *, reflection_id: int, reason: str, action: str
):
    """Append a reflection_discarded event with standard meta fields."""
    return eventlog.append(
        kind="reflection_discarded",
        content="",
        meta={
            "reflection_id": int(reflection_id),
            "reason": str(reason),
            "action": str(action),
        },
    )


def append_reflection_action(eventlog, *, content: str, style: str):
    """Append a reflection_action event with standard meta fields."""
    return eventlog.append(
        kind="reflection_action",
        content=str(content),
        meta={"style": str(style)},
    )


def append_reflection_quality(
    eventlog, *, style: str, novelty: float, has_action: bool
):
    """Append a reflection_quality event with standard meta fields."""
    return eventlog.append(
        kind="reflection_quality",
        content="",
        meta={
            "style": str(style),
            "novelty": float(novelty),
            "has_action": bool(has_action),
        },
    )


def append_reflection_check(eventlog, *, ref: int, ok: bool, reason: str):
    """Append a reflection_check event with standard meta fields."""
    return eventlog.append(
        kind="reflection_check",
        content="",
        meta={
            "ref": int(ref),
            "ok": bool(ok),
            "reason": str(reason),
        },
    )


def append_identity_adopt(eventlog, *, name: str, meta: dict):
    """Append an identity_adopt event with provided meta dict."""
    return eventlog.append(
        kind="identity_adopt",
        content=str(name),
        meta=dict(meta),
    )


def append_name_updated(
    eventlog, *, old_name: str, new_name: str, source: str = "autonomy"
):
    """Append a name_updated event with standard meta fields."""
    return eventlog.append(
        kind="name_updated",
        content="",
        meta={
            "old_name": str(old_name),
            "new_name": str(new_name),
            "source": str(source),
        },
    )


def append_identity_checkpoint(
    eventlog, *, name: str, traits: dict, commitments: dict, stage: str
):
    """Append an identity_checkpoint event with standard meta fields."""
    return eventlog.append(
        kind="identity_checkpoint",
        content="",
        meta={
            "name": str(name),
            "traits": dict(traits),
            "commitments": dict(commitments),
            "stage": str(stage),
        },
    )


def append_trait_update(eventlog, *, changes: dict, reason: str = "", **extra_meta):
    """Append a trait_update event with standard meta fields.

    Args:
        changes: Dict mapping trait names to delta values, e.g. {"openness": 0.05}
        reason: Optional reason string
        **extra_meta: Additional metadata fields to include
    """
    meta = {"changes": dict(changes)}
    if reason:
        meta["reason"] = str(reason)
    meta.update(extra_meta)
    return eventlog.append(
        kind="trait_update",
        content="",
        meta=meta,
    )


def append_commitment_rebind(
    eventlog,
    *,
    cid: str,
    old_name: str,
    new_name: str,
    identity_adopt_event_id: int | None = None,
    original_text: str | None = None,
):
    """Append a commitment_rebind event with standard meta fields via tracker API.

    Returns the last event id if emission succeeded, else 0.
    """
    try:
        from pmm.commitments.tracker import api as _tracker_api

        ok = _tracker_api.rebind_commitment(
            eventlog,
            cid=str(cid),
            old_name=str(old_name),
            new_name=str(new_name),
            identity_adopt_event_id=identity_adopt_event_id,
            original_text=original_text,
        )
        if ok:
            try:
                return int(getattr(eventlog, "get_max_id")())
            except Exception:
                return 1
        return 0
    except Exception:
        return 0


def append_reflection_forced(eventlog, *, reason: str, tick: int | None = None):
    """Append a reflection_forced event with standard meta fields."""
    meta = {"reason": str(reason)}
    if tick is not None:
        meta["tick"] = int(tick)
    return eventlog.append(
        kind="reflection_forced",
        content="",
        meta=meta,
    )


def append_metrics(eventlog, *, ias: float, gas: float):
    """Append a metrics event with IAS and GAS values."""
    return eventlog.append(
        kind="metrics",
        content="",
        meta={
            "IAS": float(ias),
            "GAS": float(gas),
        },
    )


def append_policy_update(eventlog, *, component: str, meta: dict):
    """Append a policy_update event with component and provided meta dict."""
    full_meta = {"component": str(component)}
    full_meta.update(meta)
    return eventlog.append(
        kind="policy_update",
        content="",
        meta=full_meta,
    )


def append_assessment_policy_update(eventlog, *, meta: dict):
    """Append an assessment_policy_update event with provided meta dict."""
    return eventlog.append(
        kind="assessment_policy_update",
        content="",
        meta=dict(meta),
    )


def append_bandit_arm_chosen(eventlog, *, arm: str, tick: int):
    """Append a bandit_arm_chosen event with standard meta fields."""
    return eventlog.append(
        kind="bandit_arm_chosen",
        content="",
        meta={
            "arm": str(arm),
            "tick": int(tick),
        },
    )


def append_bandit_reward(
    eventlog,
    *,
    component: str,
    arm: str,
    reward: float,
    source: str | None = None,
    window: int | None = None,
    ref: int | None = None,
):
    """Append a bandit_reward event with standard meta fields."""
    meta = {
        "component": str(component),
        "arm": str(arm),
        "reward": float(reward),
    }
    if source is not None:
        meta["source"] = str(source)
    if window is not None:
        meta["window"] = int(window)
    if ref is not None:
        meta["ref"] = int(ref)
    return eventlog.append(
        kind="bandit_reward",
        content="",
        meta=meta,
    )


def append_meta_reflection(
    eventlog,
    *,
    window: int,
    opened: int,
    closed: int,
    actions: int,
    trait_delta_abs: float,
    efficacy: float,
):
    """Append a meta_reflection event with standard meta fields."""
    return eventlog.append(
        kind="meta_reflection",
        content="",
        meta={
            "window": int(window),
            "opened": int(opened),
            "closed": int(closed),
            "actions": int(actions),
            "trait_delta_abs": float(trait_delta_abs),
            "efficacy": float(efficacy),
        },
    )


def append_self_assessment(
    eventlog,
    *,
    window: int,
    window_start_id: int,
    window_end_id: int,
    inputs_hash: str,
    opened: int,
    closed: int,
    actions: int,
    trait_delta_abs: float,
    efficacy: float,
    avg_close_lag: float,
    hit_rate: float,
    drift_util: float,
    actions_kind: str,
):
    """Append a self_assessment event with standard meta fields."""
    return eventlog.append(
        kind="self_assessment",
        content="",
        meta={
            "window": int(window),
            "window_start_id": int(window_start_id),
            "window_end_id": int(window_end_id),
            "inputs_hash": str(inputs_hash),
            "opened": int(opened),
            "closed": int(closed),
            "actions": int(actions),
            "trait_delta_abs": float(trait_delta_abs),
            "efficacy": float(efficacy),
            "avg_close_lag": float(avg_close_lag),
            "hit_rate": float(hit_rate),
            "drift_util": float(drift_util),
            "actions_kind": str(actions_kind),
        },
    )


def append_reflection_rejected(
    eventlog,
    *,
    reason: str,
    template: str = "",
    scores: dict | None = None,
    accept_mode: str = "audit",
    forced: bool = False,
):
    """Append a reflection_rejected event with standard meta fields."""
    from pmm.config import REFLECTION_REJECTED

    meta = {
        "reason": str(reason),
        "scores": scores or {},
        "accept_mode": str(accept_mode),
        "forced": bool(forced),
    }
    if template:
        meta["template"] = str(template)
    return eventlog.append(
        kind=REFLECTION_REJECTED,
        content="",
        meta=meta,
    )


def append_reflection_skipped(eventlog, *, reason: str):
    """Append a reflection_skipped event with standard meta fields."""
    from pmm.config import REFLECTION_SKIPPED

    return eventlog.append(
        kind=REFLECTION_SKIPPED,
        content="",
        meta={"reason": str(reason)},
    )
