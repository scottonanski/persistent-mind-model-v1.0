# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/context/context_query.py
"""Query helpers for ContextGraph.

Deterministic wrappers over ContextGraph structures.
"""

from __future__ import annotations

from typing import List

from pmm.context.context_graph import ContextGraph


def get_events_for_thread(context_graph: ContextGraph, thread_id: str) -> List[int]:
    """Get events in a conversation thread."""
    return context_graph.get_thread_events(thread_id)


def get_children(context_graph: ContextGraph, parent_event_id: int) -> List[int]:
    """Get child events of a parent event."""
    return context_graph.get_children(parent_event_id)


def get_events_with_tag(context_graph: ContextGraph, tag: str) -> List[int]:
    """Get events tagged with a semantic tag."""
    return context_graph.get_events_with_tag(tag)
