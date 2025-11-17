# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/concept_schemas.py
"""Schema validation and utilities for Concept Token Layer (CTL) events.

All concept events use canonical JSON payloads (sorted keys, stable separators)
and deterministic IDs based on content hashing.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Dict, List, Optional


def _canonical_json(obj: Any) -> str:
    """Return canonical JSON string for deterministic hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _compute_concept_id(payload: Dict[str, Any]) -> str:
    """Compute deterministic concept_id from payload."""
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# --- concept_define schema ---


def validate_concept_define(content: str, meta: Dict[str, Any]) -> None:
    """Validate concept_define event payload.

    Required content fields:
    - token: str (e.g., "identity.Echo", "policy.stability_v2")
    - concept_kind: str (e.g., "identity", "policy", "topic", "ontology")
    - definition: str (natural language description)
    - attributes: dict (optional metadata like priority, scope, tags)
    - version: int (default 1)

    Required meta fields:
    - concept_id: str (sha256 of canonical content)
    - source: str (e.g., "user", "autonomy_kernel", "reflection")

    Optional meta fields:
    - supersedes: str (concept_id of previous version)
    """
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"concept_define content must be valid JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("concept_define content must be a JSON object")

    # Required fields
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("concept_define requires non-empty 'token' string")

    concept_kind = data.get("concept_kind")
    if not isinstance(concept_kind, str) or not concept_kind.strip():
        raise ValueError("concept_define requires non-empty 'concept_kind' string")

    definition = data.get("definition")
    if not isinstance(definition, str) or not definition.strip():
        raise ValueError("concept_define requires non-empty 'definition' string")

    # Optional fields with type checks
    attributes = data.get("attributes", {})
    if not isinstance(attributes, dict):
        raise ValueError("concept_define 'attributes' must be a dict")

    version = data.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError("concept_define 'version' must be a positive integer")

    # Meta validation
    if not isinstance(meta, dict):
        raise ValueError("concept_define meta must be a dict")

    concept_id = meta.get("concept_id")
    if not isinstance(concept_id, str) or not concept_id:
        raise ValueError("concept_define meta requires 'concept_id' string")

    source = meta.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("concept_define meta requires 'source' string")

    # Verify concept_id matches content
    expected_id = _compute_concept_id(data)
    if concept_id != expected_id:
        raise ValueError(
            f"concept_id mismatch: expected {expected_id}, got {concept_id}"
        )

    # Optional supersedes
    supersedes = meta.get("supersedes")
    if supersedes is not None and not isinstance(supersedes, str):
        raise ValueError("concept_define meta 'supersedes' must be a string if present")


def create_concept_define_payload(
    token: str,
    concept_kind: str,
    definition: str,
    attributes: Optional[Dict[str, Any]] = None,
    version: int = 1,
    source: str = "user",
    supersedes: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    """Create validated concept_define content and meta.

    Returns: (content_json, meta_dict)
    """
    if not token or not isinstance(token, str):
        raise ValueError("token must be non-empty string")
    if not concept_kind or not isinstance(concept_kind, str):
        raise ValueError("concept_kind must be non-empty string")
    if not definition or not isinstance(definition, str):
        raise ValueError("definition must be non-empty string")
    if version < 1:
        raise ValueError("version must be positive integer")

    data = {
        "token": token.strip(),
        "concept_kind": concept_kind.strip(),
        "definition": definition.strip(),
        "attributes": attributes or {},
        "version": version,
    }

    concept_id = _compute_concept_id(data)
    content = _canonical_json(data)

    meta = {
        "concept_id": concept_id,
        "source": source,
    }
    if supersedes:
        meta["supersedes"] = supersedes

    return content, meta


# --- concept_alias schema ---


def validate_concept_alias(content: str, meta: Dict[str, Any]) -> None:
    """Validate concept_alias event payload.

    Required content fields:
    - from: str (alias token)
    - to: str (canonical token)
    - reason: str (why the alias exists)

    Required meta fields:
    - alias_id: str (sha256 of canonical content)
    - source: str
    """
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"concept_alias content must be valid JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("concept_alias content must be a JSON object")

    from_token = data.get("from")
    if not isinstance(from_token, str) or not from_token.strip():
        raise ValueError("concept_alias requires non-empty 'from' string")

    to_token = data.get("to")
    if not isinstance(to_token, str) or not to_token.strip():
        raise ValueError("concept_alias requires non-empty 'to' string")

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        raise ValueError("concept_alias 'reason' must be a string")

    # Meta validation
    if not isinstance(meta, dict):
        raise ValueError("concept_alias meta must be a dict")

    alias_id = meta.get("alias_id")
    if not isinstance(alias_id, str) or not alias_id:
        raise ValueError("concept_alias meta requires 'alias_id' string")

    source = meta.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("concept_alias meta requires 'source' string")

    # Verify alias_id matches content
    expected_id = _compute_concept_id(data)
    if alias_id != expected_id:
        raise ValueError(f"alias_id mismatch: expected {expected_id}, got {alias_id}")


def create_concept_alias_payload(
    from_token: str,
    to_token: str,
    reason: str = "",
    source: str = "user",
) -> tuple[str, Dict[str, Any]]:
    """Create validated concept_alias content and meta.

    Returns: (content_json, meta_dict)
    """
    if not from_token or not isinstance(from_token, str):
        raise ValueError("from_token must be non-empty string")
    if not to_token or not isinstance(to_token, str):
        raise ValueError("to_token must be non-empty string")

    data = {
        "from": from_token.strip(),
        "to": to_token.strip(),
        "reason": reason.strip() if reason else "",
    }

    alias_id = _compute_concept_id(data)
    content = _canonical_json(data)

    meta = {
        "alias_id": alias_id,
        "source": source,
    }

    return content, meta


# --- concept_bind_event schema ---


def validate_concept_bind_event(content: str, meta: Dict[str, Any]) -> None:
    """Validate concept_bind_event event payload.

    Required content fields:
    - event_id: int (ledger event ID)
    - tokens: List[str] (concept tokens to bind)
    - relation: str (e.g., "evidence", "mention", "counterexample")
    - weight: float (optional, default 1.0)

    Required meta fields:
    - binding_id: str (sha256 of canonical content)
    - source: str
    """
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"concept_bind_event content must be valid JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("concept_bind_event content must be a JSON object")

    event_id = data.get("event_id")
    if not isinstance(event_id, int) or event_id < 1:
        raise ValueError("concept_bind_event requires positive integer 'event_id'")

    tokens = data.get("tokens")
    if not isinstance(tokens, list) or not tokens:
        raise ValueError("concept_bind_event requires non-empty 'tokens' list")
    for tok in tokens:
        if not isinstance(tok, str) or not tok.strip():
            raise ValueError(
                "concept_bind_event 'tokens' must contain non-empty strings"
            )

    relation = data.get("relation", "evidence")
    if not isinstance(relation, str) or not relation.strip():
        raise ValueError("concept_bind_event 'relation' must be non-empty string")

    weight = data.get("weight", 1.0)
    if not isinstance(weight, (int, float)):
        raise ValueError("concept_bind_event 'weight' must be numeric")

    # Meta validation
    if not isinstance(meta, dict):
        raise ValueError("concept_bind_event meta must be a dict")

    binding_id = meta.get("binding_id")
    if not isinstance(binding_id, str) or not binding_id:
        raise ValueError("concept_bind_event meta requires 'binding_id' string")

    source = meta.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("concept_bind_event meta requires 'source' string")

    # Verify binding_id matches content
    expected_id = _compute_concept_id(data)
    if binding_id != expected_id:
        raise ValueError(
            f"binding_id mismatch: expected {expected_id}, got {binding_id}"
        )


def create_concept_bind_event_payload(
    event_id: int,
    tokens: List[str],
    relation: str = "evidence",
    weight: float = 1.0,
    source: str = "user",
) -> tuple[str, Dict[str, Any]]:
    """Create validated concept_bind_event content and meta.

    Returns: (content_json, meta_dict)
    """
    if not isinstance(event_id, int) or event_id < 1:
        raise ValueError("event_id must be positive integer")
    if not tokens or not isinstance(tokens, list):
        raise ValueError("tokens must be non-empty list")
    for tok in tokens:
        if not isinstance(tok, str) or not tok.strip():
            raise ValueError("tokens must contain non-empty strings")
    if not relation or not isinstance(relation, str):
        raise ValueError("relation must be non-empty string")
    if not isinstance(weight, (int, float)):
        raise ValueError("weight must be numeric")

    data = {
        "event_id": event_id,
        "tokens": [t.strip() for t in tokens],
        "relation": relation.strip(),
        "weight": float(weight),
    }

    binding_id = _compute_concept_id(data)
    content = _canonical_json(data)

    meta = {
        "binding_id": binding_id,
        "source": source,
    }

    return content, meta


# --- concept_relate schema ---


def validate_concept_relate(content: str, meta: Dict[str, Any]) -> None:
    """Validate concept_relate event payload.

    Required content fields:
    - from: str (source concept token)
    - to: str (target concept token)
    - relation: str (e.g., "influences", "depends_on", "implies")
    - weight: float (optional, default 1.0)

    Required meta fields:
    - relation_id: str (sha256 of canonical content)
    - source: str
    """
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"concept_relate content must be valid JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("concept_relate content must be a JSON object")

    from_token = data.get("from")
    if not isinstance(from_token, str) or not from_token.strip():
        raise ValueError("concept_relate requires non-empty 'from' string")

    to_token = data.get("to")
    if not isinstance(to_token, str) or not to_token.strip():
        raise ValueError("concept_relate requires non-empty 'to' string")

    relation = data.get("relation")
    if not isinstance(relation, str) or not relation.strip():
        raise ValueError("concept_relate requires non-empty 'relation' string")

    weight = data.get("weight", 1.0)
    if not isinstance(weight, (int, float)):
        raise ValueError("concept_relate 'weight' must be numeric")

    # Meta validation
    if not isinstance(meta, dict):
        raise ValueError("concept_relate meta must be a dict")

    relation_id = meta.get("relation_id")
    if not isinstance(relation_id, str) or not relation_id:
        raise ValueError("concept_relate meta requires 'relation_id' string")

    source = meta.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("concept_relate meta requires 'source' string")

    # Verify relation_id matches content
    expected_id = _compute_concept_id(data)
    if relation_id != expected_id:
        raise ValueError(
            f"relation_id mismatch: expected {expected_id}, got {relation_id}"
        )


def create_concept_relate_payload(
    from_token: str,
    to_token: str,
    relation: str,
    weight: float = 1.0,
    source: str = "user",
) -> tuple[str, Dict[str, Any]]:
    """Create validated concept_relate content and meta.

    Returns: (content_json, meta_dict)
    """
    if not from_token or not isinstance(from_token, str):
        raise ValueError("from_token must be non-empty string")
    if not to_token or not isinstance(to_token, str):
        raise ValueError("to_token must be non-empty string")
    if not relation or not isinstance(relation, str):
        raise ValueError("relation must be non-empty string")
    if not isinstance(weight, (int, float)):
        raise ValueError("weight must be numeric")

    data = {
        "from": from_token.strip(),
        "to": to_token.strip(),
        "relation": relation.strip(),
        "weight": float(weight),
    }

    relation_id = _compute_concept_id(data)
    content = _canonical_json(data)

    meta = {
        "relation_id": relation_id,
        "source": source,
    }

    return content, meta


# --- concept_state_snapshot schema ---


def validate_concept_state_snapshot(content: str, meta: Dict[str, Any]) -> None:
    """Validate concept_state_snapshot event payload.

    Required content fields:
    - up_to_event_id: int (ledger event ID this snapshot covers)
    - concept_counts: Dict[str, int] (token -> usage count)
    - binding_counts: Dict[str, int] (token -> number of bound events)
    - edge_counts: Dict[str, int] (relation type -> count)

    Required meta fields:
    - snapshot_id: str (sha256 of canonical content)
    - source: str
    """
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError) as e:
        raise ValueError(f"concept_state_snapshot content must be valid JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("concept_state_snapshot content must be a JSON object")

    up_to_event_id = data.get("up_to_event_id")
    if not isinstance(up_to_event_id, int) or up_to_event_id < 0:
        raise ValueError(
            "concept_state_snapshot requires non-negative integer 'up_to_event_id'"
        )

    concept_counts = data.get("concept_counts", {})
    if not isinstance(concept_counts, dict):
        raise ValueError("concept_state_snapshot 'concept_counts' must be a dict")

    binding_counts = data.get("binding_counts", {})
    if not isinstance(binding_counts, dict):
        raise ValueError("concept_state_snapshot 'binding_counts' must be a dict")

    edge_counts = data.get("edge_counts", {})
    if not isinstance(edge_counts, dict):
        raise ValueError("concept_state_snapshot 'edge_counts' must be a dict")

    # Meta validation
    if not isinstance(meta, dict):
        raise ValueError("concept_state_snapshot meta must be a dict")

    snapshot_id = meta.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("concept_state_snapshot meta requires 'snapshot_id' string")

    source = meta.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("concept_state_snapshot meta requires 'source' string")

    # Verify snapshot_id matches content
    expected_id = _compute_concept_id(data)
    if snapshot_id != expected_id:
        raise ValueError(
            f"snapshot_id mismatch: expected {expected_id}, got {snapshot_id}"
        )


def create_concept_state_snapshot_payload(
    up_to_event_id: int,
    concept_counts: Dict[str, int],
    binding_counts: Dict[str, int],
    edge_counts: Dict[str, int],
    source: str = "autonomy_kernel",
) -> tuple[str, Dict[str, Any]]:
    """Create validated concept_state_snapshot content and meta.

    Returns: (content_json, meta_dict)
    """
    if not isinstance(up_to_event_id, int) or up_to_event_id < 0:
        raise ValueError("up_to_event_id must be non-negative integer")
    if not isinstance(concept_counts, dict):
        raise ValueError("concept_counts must be dict")
    if not isinstance(binding_counts, dict):
        raise ValueError("binding_counts must be dict")
    if not isinstance(edge_counts, dict):
        raise ValueError("edge_counts must be dict")

    data = {
        "up_to_event_id": up_to_event_id,
        "concept_counts": concept_counts,
        "binding_counts": binding_counts,
        "edge_counts": edge_counts,
    }

    snapshot_id = _compute_concept_id(data)
    content = _canonical_json(data)

    meta = {
        "snapshot_id": snapshot_id,
        "source": source,
    }

    return content, meta


# --- Unified validation dispatcher ---


def validate_concept_event(kind: str, content: str, meta: Dict[str, Any]) -> None:
    """Validate any concept event based on its kind."""
    validators = {
        "concept_define": validate_concept_define,
        "concept_alias": validate_concept_alias,
        "concept_bind_event": validate_concept_bind_event,
        "concept_relate": validate_concept_relate,
        "concept_state_snapshot": validate_concept_state_snapshot,
    }

    validator = validators.get(kind)
    if validator is None:
        raise ValueError(f"Unknown concept event kind: {kind}")

    validator(content, meta)
