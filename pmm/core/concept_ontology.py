# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""CTL ontology utilities.

This module intentionally contains zero hardcoded ontology data. It only
accepts ontology payloads supplied at runtime (ideally from the ledger or a
genesis import) and writes them to the EventLog in a deterministic way.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Set, Tuple

from .concept_schemas import (
    create_concept_define_payload,
    create_concept_relate_payload,
)
from .event_log import EventLog


def seed_ctl_ontology(
    eventlog: EventLog, payload: Dict[str, Any] | None = None, source: str = "system_init"
) -> int:
    """Seed CTL ontology definitions/relationships from a supplied payload.

    Args:
        eventlog: EventLog to append events to.
        payload: Dict with "concepts" and "relationships" entries. If None, no-op.
        source: Source identifier for meta.

    Returns:
        Number of events appended.
    """
    if payload is None:
        return 0

    concepts = payload.get("concepts") or []
    relationships = payload.get("relationships") or []

    existing_concept_ids = _existing_concept_ids(eventlog)
    existing_relation_ids = _existing_relation_ids(eventlog)

    events_added = 0

    for concept in concepts:
        token, concept_kind, definition, attributes, version = _unpack_concept(concept)
        content, meta = create_concept_define_payload(
            token=token,
            concept_kind=concept_kind,
            definition=definition,
            attributes=attributes,
            version=version,
            source=source,
        )
        concept_id = meta["concept_id"]
        if concept_id in existing_concept_ids:
            continue
        eventlog.append(kind="concept_define", content=content, meta=meta)
        events_added += 1
        existing_concept_ids.add(concept_id)

    for rel in relationships:
        from_token, to_token, relation, weight = _unpack_relation(rel)
        content, meta = create_concept_relate_payload(
            from_token=from_token,
            to_token=to_token,
            relation=relation,
            weight=weight,
            source=source,
        )
        relation_id = meta["relation_id"]
        if relation_id in existing_relation_ids:
            continue
        eventlog.append(kind="concept_relate", content=content, meta=meta)
        events_added += 1
        existing_relation_ids.add(relation_id)

    return events_added


def get_ontology_stats(eventlog: EventLog) -> Dict[str, int]:
    """Compute ontology stats from the ledger (no static data)."""
    kind_counts: Dict[str, int] = {}
    for ev in eventlog.read_by_kind("concept_define"):
        try:
            data = json.loads(ev.get("content") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        concept_kind = data.get("concept_kind")
        if isinstance(concept_kind, str):
            kind_counts[concept_kind] = kind_counts.get(concept_kind, 0) + 1

    total_concepts = sum(kind_counts.values())

    # Relationships are counted by relation events, not by kind.
    total_relationships = len(eventlog.read_by_kind("concept_relate"))

    stats = {
        "total_concepts": total_concepts,
        "total_relationships": total_relationships,
    }
    for k, v in kind_counts.items():
        stats[f"{k}_concepts"] = v

    return stats


# --- internal helpers ---


def _existing_concept_ids(eventlog: EventLog) -> Set[str]:
    ids: Set[str] = set()
    for ev in eventlog.read_by_kind("concept_define"):
        meta = ev.get("meta") or {}
        cid = meta.get("concept_id")
        if isinstance(cid, str) and cid:
            ids.add(cid)
    return ids


def _existing_relation_ids(eventlog: EventLog) -> Set[str]:
    ids: Set[str] = set()
    for ev in eventlog.read_by_kind("concept_relate"):
        meta = ev.get("meta") or {}
        rid = meta.get("relation_id")
        if isinstance(rid, str) and rid:
            ids.add(rid)
    return ids


def _unpack_concept(entry: Dict[str, Any]) -> Tuple[str, str, str, Dict[str, Any], int]:
    token = _require_str(entry, "token")
    concept_kind = _require_str(entry, "concept_kind")
    definition = _require_str(entry, "definition")
    attributes = entry.get("attributes") or {}
    if not isinstance(attributes, dict):
        raise ValueError("concept attributes must be a dict")
    version = entry.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError("concept version must be positive int")
    return token, concept_kind, definition, attributes, version


def _unpack_relation(entry: Dict[str, Any]) -> Tuple[str, str, str, float]:
    from_token = _require_str(entry, "from")
    to_token = _require_str(entry, "to")
    relation = _require_str(entry, "relation")
    weight = entry.get("weight", 1.0)
    if not isinstance(weight, (int, float)):
        raise ValueError("relation weight must be numeric")
    return from_token, to_token, relation, float(weight)


def _require_str(entry: Dict[str, Any], key: str) -> str:
    val = entry.get(key)
    if not isinstance(val, str) or not val:
        raise ValueError(f"'{key}' must be a non-empty string")
    return val
