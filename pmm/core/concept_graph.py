# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/concept_graph.py
"""ConceptGraph projection for semantic relationships over EventLog.

Maintains a graph of concept tokens, their definitions, aliases, bindings to events,
and relationships between concepts. Fully rebuildable from EventLog.read_all().
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from .event_log import EventLog

if TYPE_CHECKING:
    from .meme_graph import MemeGraph


class ConceptDefinition:
    """Represents a concept token definition with version history."""

    def __init__(
        self,
        token: str,
        concept_kind: str,
        definition: str,
        attributes: Dict[str, Any],
        version: int,
        concept_id: str,
        event_id: int,
    ):
        self.token = token
        self.concept_kind = concept_kind
        self.definition = definition
        self.attributes = attributes
        self.version = version
        self.concept_id = concept_id
        self.event_id = event_id  # Event that defined this version
        self.supersedes: Optional[str] = None  # concept_id of previous version

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "concept_kind": self.concept_kind,
            "definition": self.definition,
            "attributes": self.attributes,
            "version": self.version,
            "concept_id": self.concept_id,
            "event_id": self.event_id,
            "supersedes": self.supersedes,
        }


class ConceptGraph:
    """Projection of concept tokens and their relationships over EventLog."""

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog

        # Core state
        self.concepts: Dict[str, ConceptDefinition] = {}  # token -> current definition
        self.concept_history: Dict[str, List[ConceptDefinition]] = (
            {}
        )  # token -> all versions
        self.aliases: Dict[str, str] = {}  # alias_token -> canonical_token
        self.concept_edges: Set[Tuple[str, str, str]] = (
            set()
        )  # (from_token, to_token, relation)
        self.concept_event_bindings: Dict[str, Set[int]] = (
            {}
        )  # token -> set of event_ids
        self.event_to_concepts: Dict[int, Set[str]] = {}  # event_id -> set of tokens
        # Track relations for event bindings: (token, event_id, relation)
        self.event_binding_relations: Set[Tuple[str, int, str]] = set()
        # Thread bindings (concept -> cid, cid -> concepts)
        self.concept_cid_bindings: Dict[str, Set[str]] = {}
        self.cid_to_concepts: Dict[str, Set[str]] = {}

        # Topological metadata for concepts (all rebuildable)
        # - concept_roots: earliest evidence binding for a concept token
        # - concept_tails: latest evidence binding for a concept token
        # - concept_kinds: concept_kind from concept_define (e.g. identity, policy)
        self.concept_roots: Dict[str, int] = {}
        self.concept_tails: Dict[str, int] = {}
        self.concept_kinds: Dict[str, str] = {}

        # Metadata for stats
        self.last_event_id: int = 0

    def rebuild(self, events: Optional[List[Dict[str, Any]]] = None) -> None:
        """Rebuild entire ConceptGraph from scratch."""
        self.concepts.clear()
        self.concept_history.clear()
        self.aliases.clear()
        self.concept_edges.clear()
        self.concept_event_bindings.clear()
        self.event_to_concepts.clear()
        self.event_binding_relations.clear()
        self.concept_cid_bindings.clear()
        self.cid_to_concepts.clear()
        self.concept_roots.clear()
        self.concept_tails.clear()
        self.concept_kinds.clear()
        self.last_event_id = 0

        events_list = events if events is not None else self.eventlog.read_all()
        for event in events_list:
            self._process_event(event)
            self.last_event_id = event["id"]

    def sync(self, event: Dict[str, Any]) -> None:
        """Incrementally update ConceptGraph with a new event (idempotent)."""
        event_id = event.get("id")
        if not isinstance(event_id, int):
            return

        # Idempotency: skip if we've already processed this event
        if event_id <= self.last_event_id:
            return

        self._process_event(event)
        self.last_event_id = event_id

    def _process_event(self, event: Dict[str, Any]) -> None:
        """Process a single event and update internal state."""
        kind = event.get("kind")

        if kind == "concept_define":
            self._process_concept_define(event)
        elif kind == "concept_alias":
            self._process_concept_alias(event)
        elif kind == "concept_bind_event":
            self._process_concept_bind_event(event)
        elif kind == "concept_bind_async":
            # Async bindings follow the same basic schema (event_id, tokens)
            self._process_concept_bind_event(event)
        elif kind == "identity_adoption":
            self._process_identity_adoption(event)
        elif kind == "concept_relate":
            self._process_concept_relate(event)
        elif kind == "concept_bind_thread":
            self._process_concept_bind_thread(event)
        # concept_state_snapshot is passive/observational, doesn't affect graph state

    def _process_concept_define(self, event: Dict[str, Any]) -> None:
        """Process concept_define event."""
        try:
            data = json.loads(event["content"])
            meta = event.get("meta", {})
        except (TypeError, json.JSONDecodeError):
            return

        token = data.get("token")
        if not token:
            return

        concept_def = ConceptDefinition(
            token=token,
            concept_kind=data.get("concept_kind", ""),
            definition=data.get("definition", ""),
            attributes=data.get("attributes", {}),
            version=data.get("version", 1),
            concept_id=meta.get("concept_id", ""),
            event_id=event["id"],
        )

        supersedes = meta.get("supersedes")
        if supersedes:
            concept_def.supersedes = supersedes

        # Update current definition
        self.concepts[token] = concept_def

        # Add to history
        if token not in self.concept_history:
            self.concept_history[token] = []
        self.concept_history[token].append(concept_def)

        # Cache concept kind for topology-aware queries
        if concept_def.concept_kind:
            self.concept_kinds[token] = concept_def.concept_kind

    def _process_identity_adoption(self, event: Dict[str, Any]) -> None:
        """Process identity_adoption event as implicit evidence for an identity concept.

        Binds the adopted identity token (e.g., "identity.Echo") to the
        identity_adoption event id, updating concept_event_bindings and
        event_to_concepts. Concept kind is recorded as "identity" if not
        already present from a prior concept_define.
        """
        try:
            data = json.loads(event.get("content") or "{}")
        except (TypeError, json.JSONDecodeError):
            return

        token = data.get("token")
        if not isinstance(token, str) or not token.strip():
            return
        canonical = self.canonical_token(token.strip())

        event_id = event.get("id")
        if not isinstance(event_id, int):
            return

        # Bind concept to this identity_adoption event.
        if canonical not in self.concept_event_bindings:
            self.concept_event_bindings[canonical] = set()
        self.concept_event_bindings[canonical].add(event_id)

        if event_id not in self.event_to_concepts:
            self.event_to_concepts[event_id] = set()
        self.event_to_concepts[event_id].add(canonical)

        # Maintain topological roots/tails for this concept token.
        current_root = self.concept_roots.get(canonical)
        if current_root is None or event_id < current_root:
            self.concept_roots[canonical] = event_id

        current_tail = self.concept_tails.get(canonical)
        if current_tail is None or event_id > current_tail:
            self.concept_tails[canonical] = event_id

        # If no explicit concept_kind has been defined yet, record identity.
        if canonical not in self.concept_kinds:
            self.concept_kinds[canonical] = "identity"

    def _process_concept_alias(self, event: Dict[str, Any]) -> None:
        """Process concept_alias event."""
        try:
            data = json.loads(event["content"])
        except (TypeError, json.JSONDecodeError):
            return

        from_token = data.get("from")
        to_token = data.get("to")

        if from_token and to_token:
            self.aliases[from_token] = to_token

    def _process_concept_bind_event(self, event: Dict[str, Any]) -> None:
        """Process concept_bind_event event."""
        try:
            data = json.loads(event["content"])
        except (TypeError, json.JSONDecodeError):
            return

        event_id = data.get("event_id")
        tokens = data.get("tokens", [])
        relation = data.get("relation", "")

        if not isinstance(event_id, int) or not isinstance(tokens, list):
            return

        for token in tokens:
            if not isinstance(token, str):
                continue

            # Resolve to canonical token
            canonical = self.canonical_token(token)

            # Add to concept -> events mapping
            if canonical not in self.concept_event_bindings:
                self.concept_event_bindings[canonical] = set()
            self.concept_event_bindings[canonical].add(event_id)

            # Add to event -> concepts mapping
            if event_id not in self.event_to_concepts:
                self.event_to_concepts[event_id] = set()
            self.event_to_concepts[event_id].add(canonical)

            # Maintain topological roots/tails for this concept token.
            current_root = self.concept_roots.get(canonical)
            if current_root is None or event_id < current_root:
                self.concept_roots[canonical] = event_id

            current_tail = self.concept_tails.get(canonical)
            if current_tail is None or event_id > current_tail:
                self.concept_tails[canonical] = event_id

            # Track relation if present
            if relation:
                self.event_binding_relations.add((canonical, event_id, relation))

    def _process_concept_relate(self, event: Dict[str, Any]) -> None:
        """Process concept_relate event."""
        try:
            data = json.loads(event["content"])
        except (TypeError, json.JSONDecodeError):
            return

        from_token = data.get("from")
        to_token = data.get("to")
        relation = data.get("relation")

        if not from_token or not to_token or not relation:
            return

        # Resolve to canonical tokens
        from_canonical = self.canonical_token(from_token)
        to_canonical = self.canonical_token(to_token)

        # Add edge (deduplicated by set)
        self.concept_edges.add((from_canonical, to_canonical, relation))

    def _process_concept_bind_thread(self, event: Dict[str, Any]) -> None:
        """Process concept_bind_thread event."""
        try:
            data = json.loads(event.get("content") or "{}")
        except (TypeError, json.JSONDecodeError):
            return

        cid = data.get("cid")
        tokens = data.get("tokens", [])
        relation = data.get("relation", "")

        if not cid or not isinstance(tokens, list):
            return

        for token in tokens:
            if not isinstance(token, str):
                continue
            canonical = self.canonical_token(token)

            if canonical not in self.concept_cid_bindings:
                self.concept_cid_bindings[canonical] = set()
            if cid not in self.cid_to_concepts:
                self.cid_to_concepts[cid] = set()

            self.concept_cid_bindings[canonical].add(cid)
            self.cid_to_concepts[cid].add(canonical)

            if relation:
                # Track relation in event_binding_relations for symmetry with event bindings
                self.event_binding_relations.add((canonical, -1, relation))

    # --- Query API ---

    def canonical_token(self, token: str) -> str:
        """Resolve a token to its canonical form, following alias chains."""
        if not token:
            return token

        visited = set()
        current = token

        # Follow alias chain (with cycle detection)
        while current in self.aliases:
            if current in visited:
                # Cycle detected, return current
                break
            visited.add(current)
            current = self.aliases[current]

        return current

    def get_definition(self, token: str) -> Optional[ConceptDefinition]:
        """Get the current definition for a concept token."""
        canonical = self.canonical_token(token)
        return self.concepts.get(canonical)

    def get_history(self, token: str) -> List[ConceptDefinition]:
        """Get all historical versions of a concept token."""
        canonical = self.canonical_token(token)
        return self.concept_history.get(canonical, [])

    def resolve_cids_for_concepts(self, tokens: List[str]) -> Set[str]:
        """Return all CIDs bound to any of the provided concepts."""
        cids: Set[str] = set()
        for tok in tokens or []:
            canonical = self.canonical_token(tok)
            cids.update(self.concept_cid_bindings.get(canonical, set()))
        return cids

    def resolve_concepts_for_cid(self, cid: str) -> Set[str]:
        """Return all concepts bound to a CID."""
        if not cid:
            return set()
        return set(self.cid_to_concepts.get(cid, set()))

    def events_for_concept(
        self, token: str, relation: Optional[str] = None
    ) -> List[int]:
        """Get sorted list of event IDs bound to a concept token.

        Args:
            token: Concept token (will be resolved to canonical)
            relation: Optional filter on relation type

        Returns:
            Sorted list of event IDs
        """
        canonical = self.canonical_token(token)

        if relation is None:
            # No filter - return all bound events
            event_ids = self.concept_event_bindings.get(canonical, set())
            return sorted(event_ids)

        # Filter by relation
        filtered_ids: Set[int] = set()
        for tok, eid, rel in self.event_binding_relations:
            if tok == canonical and rel == relation:
                filtered_ids.add(eid)
        return sorted(filtered_ids)

    def concepts_for_event(self, event_id: int) -> List[str]:
        """Get sorted list of concept tokens bound to an event."""
        tokens = self.event_to_concepts.get(event_id, set())
        return sorted(tokens)

    def neighbors(self, token: str, relation: Optional[str] = None) -> List[str]:
        """Get concept neighbors via concept_relate edges.

        Args:
            token: Concept token
            relation: Optional filter on relation type

        Returns:
            Sorted list of neighbor tokens (both incoming and outgoing)
        """
        canonical = self.canonical_token(token)
        neighbors_set: Set[str] = set()

        for from_tok, to_tok, rel in self.concept_edges:
            if relation is not None and rel != relation:
                continue

            if from_tok == canonical:
                neighbors_set.add(to_tok)
            elif to_tok == canonical:
                neighbors_set.add(from_tok)

        return sorted(neighbors_set)

    def outgoing_neighbors(
        self, token: str, relation: Optional[str] = None
    ) -> List[str]:
        """Get outgoing concept neighbors (token -> neighbor)."""
        canonical = self.canonical_token(token)
        neighbors_set: Set[str] = set()

        for from_tok, to_tok, rel in self.concept_edges:
            if from_tok == canonical:
                if relation is None or rel == relation:
                    neighbors_set.add(to_tok)

        return sorted(neighbors_set)

    def incoming_neighbors(
        self, token: str, relation: Optional[str] = None
    ) -> List[str]:
        """Get incoming concept neighbors (neighbor -> token)."""
        canonical = self.canonical_token(token)
        neighbors_set: Set[str] = set()

        for from_tok, to_tok, rel in self.concept_edges:
            if to_tok == canonical:
                if relation is None or rel == relation:
                    neighbors_set.add(from_tok)

        return sorted(neighbors_set)

    def concepts_for_thread(self, meme_graph: MemeGraph, cid: str) -> List[str]:
        """Get sorted list of concepts associated with a thread (via MemeGraph).

        Aggregates concepts from CID bindings and event bindings.
        """
        concepts: Set[str] = set(self.cid_to_concepts.get(cid, set()))
        thread_events = meme_graph.thread_for_cid(cid)
        for eid in thread_events:
            concepts.update(self.concepts_for_event(eid))
        return sorted(concepts)

    def threads_for_concept(
        self, meme_graph: MemeGraph, token: str, relation: Optional[str] = None
    ) -> List[str]:
        """Get sorted list of CIDs associated with a concept.

        Finds events bound to the concept, then looks up their threads via MemeGraph.
        """
        event_ids = self.events_for_concept(token, relation)
        cids: Set[str] = set()
        for eid in event_ids:
            cids.update(meme_graph.cids_for_event(eid))
        return sorted(cids)

    def stats(self) -> Dict[str, Any]:
        """Get statistics about the ConceptGraph."""
        # Count concepts by kind
        kind_counts: Dict[str, int] = {}
        for concept_def in self.concepts.values():
            kind = concept_def.concept_kind
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

        # Count edges by relation
        relation_counts: Dict[str, int] = {}
        for _, _, relation in self.concept_edges:
            relation_counts[relation] = relation_counts.get(relation, 0) + 1

        # Count bindings
        total_bindings = sum(
            len(events) for events in self.concept_event_bindings.values()
        )

        return {
            "total_concepts": len(self.concepts),
            "total_aliases": len(self.aliases),
            "total_edges": len(self.concept_edges),
            "total_bindings": total_bindings,
            "concepts_by_kind": kind_counts,
            "edges_by_relation": relation_counts,
            "last_event_id": self.last_event_id,
        }

    def all_tokens(self) -> List[str]:
        """Get sorted list of all canonical concept tokens."""
        return sorted(self.concepts.keys())

    def tokens_by_kind(self, concept_kind: str) -> List[str]:
        """Get sorted list of concept tokens of a specific kind."""
        tokens = [
            token
            for token, concept_def in self.concepts.items()
            if concept_def.concept_kind == concept_kind
        ]
        return sorted(tokens)

    def root_event_id(self, token: str) -> Optional[int]:
        """Return earliest evidence event_id bound to a concept token, if any."""
        canonical = self.canonical_token(token)
        return self.concept_roots.get(canonical)

    def tail_event_id(self, token: str) -> Optional[int]:
        """Return latest evidence event_id bound to a concept token, if any."""
        canonical = self.canonical_token(token)
        return self.concept_tails.get(canonical)

    def concept_kind(self, token: str) -> str:
        """Return concept_kind recorded for a token via concept_define, if any."""
        canonical = self.canonical_token(token)
        return self.concept_kinds.get(canonical, "")
