# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/concept_ops_compiler.py
"""Concept Operations Compiler: Parse and compile concept_ops from assistant_message.meta.

This module provides deterministic compilation of structured concept_ops JSON
into concept events, with idempotency checks to avoid duplicate events.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .concept_graph import ConceptGraph
from .concept_schemas import (
    create_concept_define_payload,
    create_concept_alias_payload,
    create_concept_bind_event_payload,
    create_concept_relate_payload,
)
from .event_log import EventLog


class ConceptOpsCompiler:
    """Compiles concept_ops from assistant_message.meta into concept events."""

    def __init__(self, eventlog: EventLog, concept_graph: ConceptGraph) -> None:
        self.eventlog = eventlog
        self.concept_graph = concept_graph

    def compile_concept_ops(
        self,
        concept_ops: Dict[str, Any],
        source: str = "assistant",
    ) -> int:
        """Compile concept_ops dict into concept events.

        Args:
            concept_ops: Dict with keys: define, aliases, bind_events, relate
            source: Source identifier for meta (default: "assistant")

        Returns:
            Number of events appended

        Expected format:
        {
            "define": [
                {
                    "token": "topic.new_topic",
                    "concept_kind": "topic",
                    "definition": "...",
                    "attributes": {...},
                    "version": 1
                }
            ],
            "aliases": [
                {
                    "from": "old_name",
                    "to": "new_name",
                    "reason": "..."
                }
            ],
            "bind_events": [
                {
                    "event_id": 123,
                    "tokens": ["topic.A", "topic.B"],
                    "relation": "evidence",
                    "weight": 0.8
                }
            ],
            "relate": [
                {
                    "from": "topic.A",
                    "to": "topic.B",
                    "relation": "influences",
                    "weight": 0.9
                }
            ]
        }
        """
        if not isinstance(concept_ops, dict):
            return 0

        events_added = 0

        # Process defines
        defines = concept_ops.get("define", [])
        if isinstance(defines, list):
            events_added += self._compile_defines(defines, source)

        # Process aliases
        aliases = concept_ops.get("aliases", [])
        if isinstance(aliases, list):
            events_added += self._compile_aliases(aliases, source)

        # Process bind_events
        bind_events = concept_ops.get("bind_events", [])
        if isinstance(bind_events, list):
            events_added += self._compile_bind_events(bind_events, source)

        # Process relate
        relates = concept_ops.get("relate", [])
        if isinstance(relates, list):
            events_added += self._compile_relates(relates, source)

        return events_added

    def _compile_defines(self, defines: List[Dict[str, Any]], source: str) -> int:
        """Compile concept_define operations with idempotency."""
        events_added = 0

        for define_op in defines:
            if not isinstance(define_op, dict):
                continue

            token = define_op.get("token")
            if not token:
                continue

            # Check if this exact definition already exists
            existing = self.concept_graph.get_definition(token)
            if existing is not None:
                # Check if definition is identical
                if (
                    existing.concept_kind == define_op.get("concept_kind", "")
                    and existing.definition == define_op.get("definition", "")
                    and existing.attributes == define_op.get("attributes", {})
                    and existing.version == define_op.get("version", 1)
                ):
                    # Identical definition exists, skip
                    continue

            # Create new definition
            try:
                content, meta = create_concept_define_payload(
                    token=define_op.get("token", ""),
                    concept_kind=define_op.get("concept_kind", ""),
                    definition=define_op.get("definition", ""),
                    attributes=define_op.get("attributes", {}),
                    version=define_op.get("version", 1),
                    source=source,
                    supersedes=define_op.get("supersedes"),
                )

                self.eventlog.append(kind="concept_define", content=content, meta=meta)
                events_added += 1
            except (ValueError, TypeError):
                # Skip invalid operations
                continue

        return events_added

    def _compile_aliases(self, aliases: List[Dict[str, Any]], source: str) -> int:
        """Compile concept_alias operations with idempotency."""
        events_added = 0

        for alias_op in aliases:
            if not isinstance(alias_op, dict):
                continue

            from_token = alias_op.get("from")
            to_token = alias_op.get("to")

            if not from_token or not to_token:
                continue

            # Check if this alias already exists
            existing_canonical = self.concept_graph.canonical_token(from_token)
            if existing_canonical == to_token:
                # Alias already exists, skip
                continue

            # Create alias
            try:
                content, meta = create_concept_alias_payload(
                    from_token=from_token,
                    to_token=to_token,
                    reason=alias_op.get("reason", ""),
                    source=source,
                )

                self.eventlog.append(kind="concept_alias", content=content, meta=meta)
                events_added += 1
            except (ValueError, TypeError):
                continue

        return events_added

    def _compile_bind_events(
        self, bind_events: List[Dict[str, Any]], source: str
    ) -> int:
        """Compile concept_bind_event operations with idempotency."""
        events_added = 0

        for bind_op in bind_events:
            if not isinstance(bind_op, dict):
                continue

            event_id = bind_op.get("event_id")
            tokens = bind_op.get("tokens", [])

            if not isinstance(event_id, int) or not isinstance(tokens, list):
                continue

            # Check if event exists
            if not self.eventlog.exists(event_id):
                continue

            # Filter out tokens that are already bound to this event
            existing_concepts = set(self.concept_graph.concepts_for_event(event_id))
            new_tokens = [
                t
                for t in tokens
                if isinstance(t, str)
                and self.concept_graph.canonical_token(t) not in existing_concepts
            ]

            if not new_tokens:
                # All tokens already bound, skip
                continue

            # Create binding
            try:
                content, meta = create_concept_bind_event_payload(
                    event_id=event_id,
                    tokens=new_tokens,
                    relation=bind_op.get("relation", "evidence"),
                    weight=bind_op.get("weight", 1.0),
                    source=source,
                )

                self.eventlog.append(
                    kind="concept_bind_event", content=content, meta=meta
                )
                events_added += 1
            except (ValueError, TypeError):
                continue

        return events_added

    def _compile_relates(self, relates: List[Dict[str, Any]], source: str) -> int:
        """Compile concept_relate operations with idempotency."""
        events_added = 0

        for relate_op in relates:
            if not isinstance(relate_op, dict):
                continue

            from_token = relate_op.get("from")
            to_token = relate_op.get("to")
            relation = relate_op.get("relation")

            if not from_token or not to_token or not relation:
                continue

            # Resolve to canonical tokens
            from_canonical = self.concept_graph.canonical_token(from_token)
            to_canonical = self.concept_graph.canonical_token(to_token)

            # Check if this relationship already exists
            if (
                from_canonical,
                to_canonical,
                relation,
            ) in self.concept_graph.concept_edges:
                # Relationship exists, skip
                continue

            # Create relationship
            try:
                content, meta = create_concept_relate_payload(
                    from_token=from_canonical,
                    to_token=to_canonical,
                    relation=relation,
                    weight=relate_op.get("weight", 1.0),
                    source=source,
                )

                self.eventlog.append(kind="concept_relate", content=content, meta=meta)
                events_added += 1
            except (ValueError, TypeError):
                continue

        return events_added


def compile_concept_ops(
    eventlog: EventLog,
    concept_ops: Dict[str, Any],
    source: str = "test",
) -> int:
    """Compile concept_ops JSON directly into concept events.

    This is a simplified wrapper for testing. In production, use
    compile_assistant_message_concepts which extracts concept_ops
    from assistant message meta.

    Args:
        eventlog: EventLog instance
        concept_ops: Dictionary with define/bind_events/relate/aliases lists
        source: Source identifier for meta (default: "test")

    Returns:
        Number of events added
    """
    cg = ConceptGraph(eventlog)
    cg.rebuild(eventlog.read_all())

    compiler = ConceptOpsCompiler(eventlog, cg)
    return compiler.compile_concept_ops(concept_ops, source=source)


def compile_assistant_message_concepts(
    eventlog: EventLog,
    concept_graph: ConceptGraph,
    assistant_message_event: Dict[str, Any],
) -> int:
    """Extract and compile concept_ops from an assistant_message event.

    Args:
        eventlog: EventLog instance
        concept_graph: ConceptGraph instance
        assistant_message_event: The assistant_message event dict

    Returns:
        Number of concept events appended
    """
    if assistant_message_event.get("kind") != "assistant_message":
        return 0

    meta = assistant_message_event.get("meta", {})
    concept_ops = meta.get("concept_ops")

    if not isinstance(concept_ops, dict):
        return 0

    compiler = ConceptOpsCompiler(eventlog, concept_graph)
    return compiler.compile_concept_ops(concept_ops, source="assistant")
