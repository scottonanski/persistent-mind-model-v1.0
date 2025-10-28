"""
Deterministic event narratives with meta fallback and epistemic status.
No regex, no environment flags, no writes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

EventRow = dict[str, Any]


@dataclass(frozen=True)
class EventNarrative:
    """Structured representation of an event narrative with epistemic status."""

    text: str
    confidence: Literal["high", "medium", "none"]
    source: Literal["content", "meta", "none"]


def _decode_meta(meta_raw: str | Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Decode meta payload robustly, tolerating strings, dicts, or None."""
    if meta_raw is None:
        return {}
    if isinstance(meta_raw, str):
        try:
            return json.loads(meta_raw)
        except Exception:
            return {}
    if isinstance(meta_raw, Mapping):
        return dict(meta_raw)
    return {}


def get_event_narrative(ledger, event_id: int) -> EventNarrative:
    """Lookup event and produce deterministic narrative with epistemic status."""
    event = ledger.get_event(event_id)
    if not event:
        return EventNarrative(f"Event #{event_id} does not exist", "none", "none")
    return eventrow_to_narrative(event)


def eventrow_to_narrative(event: EventRow) -> EventNarrative:
    """Convert ledger event row to narrative without additional reads."""
    content = (event.get("content") or "").strip()
    if content:
        return EventNarrative(content, "high", "content")

    meta = _decode_meta(event.get("meta"))
    text = _from_meta(str(event.get("kind", "unknown")), meta)
    if text:
        return EventNarrative(text, "medium", "meta")

    kind = str(event.get("kind", "unknown"))
    eid = event.get("id", "?")
    return EventNarrative(f"Event #{eid} ({kind})", "none", "none")


def _from_meta(kind: str, meta: Mapping[str, Any]) -> str | None:
    """Produce deterministic narrative text from structured metadata."""
    if kind == "llm_latency":
        provider = str(meta.get("provider", "?"))
        model = str(meta.get("model", "?"))
        op = str(meta.get("op", "operation"))
        duration_ms: float | None
        if "ms" in meta:
            try:
                duration_ms = float(meta["ms"])
            except Exception:
                duration_ms = None
        elif "seconds" in meta:
            try:
                duration_ms = float(meta["seconds"]) * 1000.0
            except Exception:
                duration_ms = None
        else:
            duration_ms = None
        tick = meta.get("tick", "?")
        duration_txt = f"{duration_ms:.2f}ms" if duration_ms is not None else "?ms"
        return f"{provider}::{model} {op} completed in {duration_txt} (tick {tick})"

    if kind == "autonomy_tick":
        tick = meta.get("tick", "?")
        telemetry = meta.get("telemetry") or {}
        reflect = meta.get("reflect") or {}
        status = (
            "reflected"
            if reflect.get("did")
            else f"skipped ({reflect.get('reason', 'unknown')})"
        )
        ias = telemetry.get("IAS", "?")
        gas = telemetry.get("GAS", "?")
        return f"Autonomy tick {tick}: {status}, IAS={ias}, GAS={gas}"

    if kind == "reflection_skipped":
        reason = meta.get("reason", "unspecified")
        return f"Reflection skipped: {reason}"

    if kind == "commitment_open":
        text = meta.get("text", meta.get("original_text", ""))
        try:
            score = float(meta.get("semantic_score", 0.0))
        except Exception:
            score = 0.0
        return f"Commitment opened (score={score:.2f}): {text}"

    if kind == "stage_progress":
        stage = meta.get("stage", "?")
        return f"Stage progression to {stage}"

    if kind == "bandit_reward":
        arm = meta.get("arm", "?")
        reward = meta.get("reward", "?")
        return f"Bandit arm {arm} reward: {reward}"

    if kind == "invariant_violation":
        violation = meta.get("violation", "unspecified")
        return f"Invariant violation: {violation}"

    return None
