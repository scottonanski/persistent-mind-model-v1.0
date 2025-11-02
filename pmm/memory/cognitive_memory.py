"""
AI-Centric Cognitive Memory System

This memory system is designed specifically for AI cognition, not human imitation.
It implements three tiers optimized for how AI actually processes information:

1. **Active Context (Tier 1)**: Current working memory with precise recall
2. **Semantic Index (Tier 2)**: Compressed embeddings for pattern recognition
3. **Strategic Archive (Tier 3)**: Long-term storage with intelligent retrieval

Key differences from human-like memory:
- No intentional "forgetting" - all data is preserved
- Retrieval is based on relevance, not recency
- Confabulation is treated as a bug, not a feature
- Memory scales with computational resources, not biological limits
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from pmm.runtime.embeddings import compute_embedding, cosine_similarity
from pmm.storage.eventlog import EventLog

logger = logging.getLogger(__name__)


class MemoryTier(Enum):
    ACTIVE = "active"
    SEMANTIC = "semantic"
    ARCHIVE = "archive"


@dataclass
class MemoryFragment:
    """A single memory fragment with metadata for intelligent retrieval."""

    content: str
    embedding: np.ndarray
    timestamp: float
    event_id: int
    tier: MemoryTier
    importance_score: float = 0.0
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    context_links: list[int] = field(default_factory=list)  # Related event IDs


@dataclass
class RetrievalQuery:
    """A query for memory retrieval with relevance parameters."""

    query: str
    embedding: np.ndarray
    min_relevance: float = 0.5
    max_results: int = 10
    tier_filter: MemoryTier | None = None
    time_weight: float = 0.1  # How much to weight recency
    importance_weight: float = 0.3  # How much to weight importance


class CognitiveMemory:
    """
    AI-optimized memory system that prioritizes utility over human imitation.

    Design principles:
    1. Complete preservation - no data loss unless explicitly purged
    2. Intelligent retrieval - relevance-based access to all memories
    3. Adaptive importance - scoring based on usage and outcomes
    4. Context awareness - understanding relationships between memories
    """

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog
        self.fragments: dict[int, MemoryFragment] = {}
        self.semantic_index: dict[str, list[int]] = {}  # Tag -> event_ids
        self._is_built = False

    def build_memory_index(self) -> None:
        """Build the complete memory index from the event log."""
        logger.info("Building cognitive memory index...")

        events = self.eventlog.read_all()
        for event in events:
            self._index_event(event)

        self._is_built = True
        logger.info(f"Indexed {len(self.fragments)} memory fragments")

    def _index_event(self, event: dict) -> None:
        """Index a single event into the memory system."""
        event_id = event["id"]
        content = self._extract_content(event)

        if not content:
            return

        embedding = compute_embedding(content)
        importance = self._calculate_importance(event)
        tags = self._extract_tags(event)

        fragment = MemoryFragment(
            content=content,
            embedding=embedding,
            timestamp=event.get("timestamp", time.time()),
            event_id=event_id,
            tier=self._determine_tier(event),
            importance_score=importance,
            tags=tags,
        )

        self.fragments[event_id] = fragment

        # Update semantic index
        for tag in tags:
            if tag not in self.semantic_index:
                self.semantic_index[tag] = []
            self.semantic_index[tag].append(event_id)

    def _extract_content(self, event: dict) -> str:
        """Extract searchable content from an event."""
        kind = event.get("kind", "")

        content_parts = []

        # Add event kind
        content_parts.append(f"kind: {kind}")

        # Add main content based on event type
        if kind in ["user_message", "assistant_message"]:
            content_parts.append(event.get("content", ""))
        elif kind == "commitment":
            content_parts.append(event.get("description", ""))
            content_parts.append(event.get("status", ""))
        elif kind == "reflection":
            content_parts.append(event.get("prompt", ""))
            content_parts.append(event.get("response", ""))
        elif kind == "policy_update":
            content_parts.append(f"component: {event.get('component', '')}")
            content_parts.append(f"params: {event.get('params', {})}")
        elif kind == "autonomy_tick":
            content_parts.append(f"metrics: {event.get('metrics', {})}")
            content_parts.append(f"stage: {event.get('stage', '')}")

        # Add metadata
        for key, value in event.items():
            if key not in ["id", "timestamp", "prev_hash", "hash"]:
                if isinstance(value, (str, int, float, bool)):
                    content_parts.append(f"{key}: {value}")

        return " ".join(str(part) for part in content_parts if part)

    def _calculate_importance(self, event: dict) -> float:
        """Calculate importance score for an event."""
        base_score = 0.1

        kind = event.get("kind", "")

        # Higher importance for significant events
        importance_by_kind = {
            "commitment": 0.8,
            "reflection": 0.7,
            "policy_update": 0.6,
            "identity_adoption": 0.9,
            "user_message": 0.4,
            "assistant_message": 0.3,
            "autonomy_tick": 0.2,
        }

        base_score = importance_by_kind.get(kind, 0.1)

        # Boost for events with rich content
        content_length = len(str(event.get("content", "")))
        if content_length > 500:
            base_score += 0.1
        elif content_length > 100:
            base_score += 0.05

        return min(base_score, 1.0)

    def _extract_tags(self, event: dict) -> list[str]:
        """Extract tags for semantic indexing."""
        tags = []

        # Event kind tag
        tags.append(f"kind:{event.get('kind', '')}")

        # Content-based tags
        content = str(event.get("content", "")).lower()

        # Commitment-related tags
        if "commit" in content:
            tags.append("commitment")
        if "goal" in content or "objective" in content:
            tags.append("goal")
        if "complete" in content or "done" in content:
            tags.append("completion")

        # Reflection-related tags
        if "reflect" in content or "thinking" in content:
            tags.append("reflection")
        if "learn" in content or "insight" in content:
            tags.append("learning")

        # Identity-related tags
        if "identity" in content or "name" in content:
            tags.append("identity")

        # Metric-related tags
        if "metric" in content or "score" in content:
            tags.append("metrics")

        return tags

    def _determine_tier(self, event: dict) -> MemoryTier:
        """Determine which memory tier an event belongs to."""
        # Recent events go to active
        event_time = event.get("timestamp", time.time())
        if time.time() - event_time < 3600:  # Last hour
            return MemoryTier.ACTIVE

        # Important events stay in semantic
        if self._calculate_importance(event) > 0.5:
            return MemoryTier.SEMANTIC

        # Everything else goes to archive
        return MemoryTier.ARCHIVE

    def retrieve(self, query: RetrievalQuery) -> list[MemoryFragment]:
        """Retrieve relevant memory fragments based on a query."""
        if not self._is_built:
            self.build_memory_index()

        candidates = list(self.fragments.values())

        # Filter by tier if specified
        if query.tier_filter:
            candidates = [f for f in candidates if f.tier == query.tier_filter]

        # Calculate relevance scores
        scored_fragments = []
        for fragment in candidates:
            semantic_sim = cosine_similarity(query.embedding, fragment.embedding)

            # Time relevance (more recent = higher score)
            time_factor = 1.0 / (
                1.0 + (time.time() - fragment.timestamp) / 86400
            )  # Decay over days

            # Importance factor
            importance_factor = fragment.importance_score

            # Combined relevance score
            relevance = (
                semantic_sim * (1.0 - query.time_weight - query.importance_weight)
                + time_factor * query.time_weight
                + importance_factor * query.importance_weight
            )

            if relevance >= query.min_relevance:
                scored_fragments.append((fragment, relevance))

        # Sort by relevance and return top results
        scored_fragments.sort(key=lambda x: x[1], reverse=True)

        # Update access statistics
        for fragment, _ in scored_fragments[: query.max_results]:
            fragment.access_count += 1
            fragment.last_accessed = time.time()

        return [fragment for fragment, _ in scored_fragments[: query.max_results]]

    def query(self, query_text: str, **kwargs) -> list[MemoryFragment]:
        """Convenient method to query memory with text."""
        embedding = compute_embedding(query_text)
        query = RetrievalQuery(query=query_text, embedding=embedding, **kwargs)
        return self.retrieve(query)

    def get_related_memories(
        self, event_id: int, max_results: int = 5
    ) -> list[MemoryFragment]:
        """Get memories related to a specific event."""
        if event_id not in self.fragments:
            return []

        target_fragment = self.fragments[event_id]
        query = RetrievalQuery(
            query=target_fragment.content,
            embedding=target_fragment.embedding,
            max_results=max_results + 1,  # +1 to exclude the original
        )

        related = self.retrieve(query)
        # Exclude the original fragment
        return [f for f in related if f.event_id != event_id][:max_results]

    def update_importance(self, event_id: int, new_score: float) -> None:
        """Update importance score for a memory fragment."""
        if event_id in self.fragments:
            self.fragments[event_id].importance_score = min(max(new_score, 0.0), 1.0)

    def get_memory_stats(self) -> dict[str, Any]:
        """Get statistics about the memory system."""
        if not self._is_built:
            return {"status": "not_built"}

        tier_counts = {}
        for tier in MemoryTier:
            tier_counts[tier.value] = sum(
                1 for f in self.fragments.values() if f.tier == tier
            )

        avg_importance = sum(f.importance_score for f in self.fragments.values()) / len(
            self.fragments
        )

        return {
            "total_fragments": len(self.fragments),
            "tier_distribution": tier_counts,
            "average_importance": avg_importance,
            "total_tags": len(self.semantic_index),
            "most_accessed": sorted(
                self.fragments.values(), key=lambda f: f.access_count, reverse=True
            )[:5],
        }
