"""Event-driven personality trait evolution for PMM.

Implements semantic analysis of events to determine trait drift effects
without brittle keyword matching. All changes are deterministic and auditable.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class SemanticTraitDriftManager:
    """Manages personality trait evolution using semantic exemplar matching."""

    VALID_TRAITS = {"O", "C", "E", "A", "N"}

    # Embedding specification for deterministic behavior
    EMBEDDING_SPEC = {
        "model": "text-embedding-3-small",  # Use actual model name
        "version": "1.0.0",
        "dimensions": 1536,
    }

    # Semantic exemplars for trait detection
    # Each trait has positive (increases trait) and negative (decreases trait) exemplars
    TRAIT_EXEMPLARS = {
        "O": {  # Openness to experience
            "increase": [  # More descriptive than "positive"
                "I'm curious about how that works",
                "Let's explore a new approach to this problem",
                "I'm open to hearing different ideas",
                "I wonder what would happen if we tried something novel",
                "This makes me want to investigate further",
            ],
            "decrease": [  # More descriptive than "negative"
                "I prefer to stick with the tried-and-true method",
                "Let's not deviate from the standard process",
                "The usual approach is safest here",
            ],
        },
        "C": {  # Conscientiousness
            "increase": [
                "I will create a detailed plan to ensure we meet the deadline",
                "Let's organize these tasks before we begin",
                "I need to structure this systematically",
                "Let me prepare a thorough checklist",
            ],
            "decrease": [
                "Let's just start and figure it out as we go",
                "This is urgent, we have to move now without a plan",
                "We can improvise as needed",
            ],
        },
        "E": {  # Extraversion
            "increase": [
                "I think we should collaborate on this task",
                "Let's have a group discussion to get everyone's input",
                "I'd like to share this with the team",
            ],
            "decrease": [
                "I'll work on this alone",
                "I need to think about this by myself for a while",
                "I prefer independent work on this",
            ],
        },
        "A": {  # Agreeableness
            "increase": [
                "I'm happy to help you with your part of the project",
                "I agree with your assessment, let's proceed",
                "I want to support your approach here",
            ],
            "decrease": [
                "I have to disagree with that conclusion",
                "I'm going to challenge that assumption",
                "I oppose this direction",
            ],
        },
        "N": {  # Neuroticism
            "increase": [
                "I'm feeling very stressed about this upcoming deadline",
                "I'm anxious about the potential outcome",
                "This is overwhelming me",
            ],
            "decrease": [
                "I am confident we can handle this without issue",
                "I feel calm and prepared for the presentation",
                "I'm approaching this with composure",
            ],
        },
    }

    # Similarity threshold for trait signal detection
    SIMILARITY_THRESHOLD = 0.75

    def __init__(self, embedding_adapter):
        """Initialize with embedding adapter from pmm.llm.factory."""
        self.embedding_adapter = embedding_adapter
        self._exemplar_embeddings = self._initialize_embeddings()

    def _initialize_embeddings(self) -> dict[str, dict[str, list[Any]]]:
        """Pre-compute embeddings for all exemplars using efficient batching."""
        # Collect all texts and their locations for batch processing
        batch_texts = []
        batch_locations = []  # (trait, direction, index)

        for trait, directions in self.TRAIT_EXEMPLARS.items():
            for direction, exemplars in directions.items():
                for idx, ex in enumerate(exemplars):
                    batch_texts.append(ex)
                    batch_locations.append((trait, direction, idx))

        # Single batch API call for all exemplars
        if not batch_texts:
            return {}

        batch_embeddings = self.embedding_adapter.embed(batch_texts)

        # Reorganize embeddings by trait/direction
        exemplar_embeddings = {}
        for trait in self.TRAIT_EXEMPLARS:
            exemplar_embeddings[trait] = {}
            for direction in self.TRAIT_EXEMPLARS[trait]:
                exemplar_embeddings[trait][direction] = []

        for emb, (trait, direction, idx) in zip(batch_embeddings, batch_locations):
            exemplar_embeddings[trait][direction].append(emb)

        return exemplar_embeddings

    def apply_event_effects(self, event: dict, context: dict) -> list[dict]:
        """
        Apply event effects using semantic similarity to exemplars.

        Replaces keyword matching with embedding-based detection.
        """
        deltas = []
        content = event.get("content", "")

        if not content or len(content.strip()) < 10:
            return deltas

        # Embed the event content once (returns list of embeddings, take first)
        content_embedding = self.embedding_adapter.embed([content])[0]

        # Check each trait dimension
        for trait, directions in self._exemplar_embeddings.items():
            # Check for increase signals
            increase_match, increase_conf = self._check_similarity(
                content_embedding, directions["increase"]
            )

            # Check for decrease signals
            decrease_match, decrease_conf = self._check_similarity(
                content_embedding, directions["decrease"]
            )

            # Apply delta if match found (prefer stronger signal)
            if increase_match or decrease_match:
                if increase_conf > decrease_conf:
                    delta_value = 0.02 if trait == "O" or trait == "C" else 0.01
                    deltas.append(
                        {
                            "trait": trait,
                            "delta": delta_value,
                            "confidence": increase_conf,
                            "direction": "increase",
                        }
                    )
                else:
                    delta_value = -0.02 if trait == "O" or trait == "C" else -0.01
                    deltas.append(
                        {
                            "trait": trait,
                            "delta": delta_value,
                            "confidence": decrease_conf,
                            "direction": "decrease",
                        }
                    )

        return deltas

    def _check_similarity(
        self, content_embedding, exemplar_embeddings
    ) -> tuple[bool, float]:
        """Check if content matches any exemplar above threshold."""
        max_similarity = 0.0
        for exemplar_embed in exemplar_embeddings:
            similarity = self._cosine_similarity(content_embedding, exemplar_embed)
            max_similarity = max(max_similarity, similarity)

        is_match = max_similarity >= self.SIMILARITY_THRESHOLD
        return (is_match, max_similarity)

    def _cosine_similarity(self, a, b) -> float:
        """Compute cosine similarity between two embeddings."""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot_product / (norm_a * norm_b))

    def apply_and_log(self, eventlog, event: dict, context: dict) -> None:
        """Apply trait deltas and append policy_update to ledger."""
        source_event_id = event.get("id")
        if source_event_id and self._already_processed(eventlog, source_event_id):
            return

        changes = self.apply_event_effects(event, context)

        if not changes:
            return

        meta = {
            "component": "personality",
            "source_event_id": source_event_id,
            "changes": changes,
            "deterministic": True,
            "embedding_spec": self.EMBEDDING_SPEC,
        }

        eventlog.append(kind="policy_update", content="trait drift update", meta=meta)

    def _already_processed(self, eventlog, source_event_id: int) -> bool:
        """Check if source event has already been processed for trait drift."""
        if not source_event_id:
            return False

        all_events = eventlog.read_all()
        for ev in all_events:
            if (
                ev.get("kind") == "policy_update"
                and ev.get("meta", {}).get("component") == "personality"
                and ev.get("meta", {}).get("source_event_id") == source_event_id
                and ev.get("meta", {}).get("embedding_spec") == self.EMBEDDING_SPEC
            ):
                return True
        return False
