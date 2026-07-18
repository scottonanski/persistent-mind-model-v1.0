"""Deterministic attribution metadata for CTL binding assertions."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Dict, Optional

BINDING_ATTRIBUTION_PROTOCOL = "concept_binding_attribution.v1"
VALID_BINDING_ORIGINS = {
    "model_declared",
    "runtime_continuity_fallback",
    "runtime_meditation",
    "runtime_autonomy",
    "runtime_claim_projection",
    "runtime_inferred_indexing",
    "index_backfill",
    "operator_declared",
}
LEGACY_BINDING_ORIGIN = "legacy_unknown"


def binding_attribution_meta(
    *,
    source: str,
    binding_origin: str,
    kind: str,
    content: str,
    origin_event_id: Optional[int] = None,
    derived_from_binding_event_id: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return validated protocol-v1 metadata for one binding assertion."""
    if binding_origin not in VALID_BINDING_ORIGINS:
        raise ValueError(f"unsupported binding_origin: {binding_origin}")
    if binding_origin == "model_declared" and not _positive_int(origin_event_id):
        raise ValueError("model_declared bindings require origin_event_id")
    if origin_event_id is not None and not _positive_int(origin_event_id):
        raise ValueError("origin_event_id must be a positive integer")
    if derived_from_binding_event_id is not None and not _positive_int(
        derived_from_binding_event_id
    ):
        raise ValueError("derived_from_binding_event_id must be a positive integer")

    assertion = {
        "binding_origin": binding_origin,
        "content": content,
        "derived_from_binding_event_id": derived_from_binding_event_id,
        "kind": kind,
        "origin_event_id": origin_event_id,
    }
    canonical = json.dumps(assertion, sort_keys=True, separators=(",", ":"))
    meta: Dict[str, Any] = dict(extra or {})
    meta.update(
        {
            "source": source,
            "binding_protocol": BINDING_ATTRIBUTION_PROTOCOL,
            "binding_origin": binding_origin,
            "attribution_id": sha256(canonical.encode("utf-8")).hexdigest(),
        }
    )
    if origin_event_id is not None:
        meta["origin_event_id"] = origin_event_id
    if derived_from_binding_event_id is not None:
        meta["derived_from_binding_event_id"] = derived_from_binding_event_id
    return meta


def projected_binding_origin(meta: Dict[str, Any] | None) -> str:
    """Classify legacy bindings at projection time without rewriting them."""
    candidate = (meta or {}).get("binding_origin")
    if (
        (meta or {}).get("binding_protocol") == BINDING_ATTRIBUTION_PROTOCOL
        and candidate in VALID_BINDING_ORIGINS
    ):
        return str(candidate)
    return LEGACY_BINDING_ORIGIN


def validate_binding_attribution_meta(meta: Dict[str, Any]) -> None:
    """Validate metadata only when it opts into attribution protocol v1."""
    if meta.get("binding_protocol") != BINDING_ATTRIBUTION_PROTOCOL:
        return
    origin = meta.get("binding_origin")
    if origin not in VALID_BINDING_ORIGINS:
        raise ValueError(f"unsupported binding_origin: {origin}")
    if not isinstance(meta.get("source"), str) or not meta["source"]:
        raise ValueError("attributed bindings require source")
    if not isinstance(meta.get("attribution_id"), str) or not meta["attribution_id"]:
        raise ValueError("attributed bindings require attribution_id")
    origin_event_id = meta.get("origin_event_id")
    derived_id = meta.get("derived_from_binding_event_id")
    if origin == "model_declared" and not _positive_int(origin_event_id):
        raise ValueError("model_declared bindings require origin_event_id")
    if origin_event_id is not None and not _positive_int(origin_event_id):
        raise ValueError("origin_event_id must be a positive integer")
    if derived_id is not None and not _positive_int(derived_id):
        raise ValueError("derived_from_binding_event_id must be a positive integer")


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
