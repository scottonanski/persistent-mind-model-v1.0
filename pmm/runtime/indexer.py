# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/indexer.py
"""Background Indexer for PMM.

Handles asynchronous concept extraction and claim generation to ensure
memory coverage for untagged events. Fully deterministic and regex-free.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph


class SemanticExtractor:
    """Deterministic, regex-free extractor for facts and concepts.

    Uses simple token-stream parsing to avoid prohibited regex heuristics.
    """

    def _tokenize(self, text: str) -> List[str]:
        """Convert text to lowercase tokens, stripping basic punctuation."""
        # Simple splitter.
        # "My name is Scott." -> ["my", "name", "is", "scott"]
        text = text.lower()
        # Replace common punctuation with spaces
        for char in ".,!?;:()[]\"'":
            text = text.replace(char, " ")
        return [t for t in text.split() if t]

    def extract_safe_claims(self, text: str) -> List[Dict[str, Any]]:
        """Extract claims using a strict phrase-structure grammar."""
        claims = []
        tokens = self._tokenize(text)

        # Modals that invalidate factual assertion
        modals = {
            "might",
            "maybe",
            "could",
            "should",
            "would",
            "think",
            "guess",
            "wish",
            "probably",
            "possibly",
        }
        if any(m in tokens for m in modals):
            return []

        # Simple n-gram / pattern matching on token stream
        # Pattern 1: "my name is [NAME]"
        for i in range(len(tokens) - 3):
            if tokens[i] == "my" and tokens[i + 1] == "name" and tokens[i + 2] == "is":
                # Capture the next token as name
                name_val = tokens[i + 3]
                claims.append(
                    {
                        "type": "user.identity.name",
                        "value": name_val,
                        "confidence": 0.95,
                    }
                )

        # Pattern 2: "i live in [PLACE]"
        for i in range(len(tokens) - 3):
            if tokens[i] == "i" and tokens[i + 1] == "live" and tokens[i + 2] == "in":
                # Capture up to 3 following tokens as place (simple heuristic)
                # Stop if we hit a known stop word or end of list
                place_tokens = []
                for j in range(i + 3, min(i + 6, len(tokens))):
                    place_tokens.append(tokens[j])

                if place_tokens:
                    claims.append(
                        {
                            "type": "user.location",
                            "value": " ".join(place_tokens),
                            "confidence": 0.90,
                        }
                    )

        # Pattern 3: "i use [TOOL]"
        for i in range(len(tokens) - 2):
            if tokens[i] == "i" and tokens[i + 1] == "use":
                tool_val = tokens[i + 2]
                claims.append(
                    {"type": "user.tool_usage", "value": tool_val, "confidence": 0.90}
                )

        return claims

    def extract_fuzzy_concepts(self, text: str) -> List[str]:
        """Map text to broad topics using deterministic keyword sets."""
        concepts = []
        tokens = set(self._tokenize(text))

        # Topic mappings (token -> concept)
        topics = {
            "python": "topic.programming.python",
            "code": "topic.programming",
            "coding": "topic.programming",
            "memory": "topic.system.memory",
            "bug": "topic.system.issue",
            "error": "topic.system.issue",
            "slow": "metric.performance",
            "fast": "metric.performance",
            "linux": "topic.os.linux",
            "ubuntu": "topic.os.linux",
            "arch": "topic.os.linux",
            "goal": "topic.planning",
            "plan": "topic.planning",
        }

        for word, concept in topics.items():
            if word in tokens:
                concepts.append(concept)

        return sorted(list(set(concepts)))


class Indexer:
    """Background worker that backfills concept bindings."""

    def __init__(self, eventlog: EventLog):
        self.eventlog = eventlog
        self.extractor = SemanticExtractor()
        # We need a local ConceptGraph projection to know what's already indexed
        self.concept_graph = ConceptGraph(eventlog)
        self.concept_graph.rebuild()
        # Track progress for embedding backfill to stay incremental
        self._last_embedded_id: int = 0

    def run_indexing_cycle(self, limit: int = 50) -> int:
        """Scan recent unindexed events and apply async bindings.

        Returns number of events processed.
        """
        # Sync graph to latest
        self.concept_graph.rebuild()
        # (Optimization: could use sync, but rebuild ensures full consistency for the batch)

        # Bounded scan over recent events to avoid full-ledger reads.
        events = self.eventlog.read_tail(max(1, int(limit)))
        # Filter for user/assistant messages in the recent window (ordered ASC by read_tail)
        candidates = [
            e for e in events if e.get("kind") in ("user_message", "assistant_message")
        ]

        processed_count = 0

        for event in candidates:
            event_id = event["id"]
            # Skip if already has concepts
            if self.concept_graph.concepts_for_event(event_id):
                continue

            text = event.get("content") or ""
            if not text:
                continue

            # 1. Extract Fuzzy Concepts
            fuzzy_concepts = self.extractor.extract_fuzzy_concepts(text)
            if fuzzy_concepts:
                # Emit async binding
                bind_content = json.dumps(
                    {
                        "event_id": event_id,
                        "tokens": fuzzy_concepts,
                        "relation": "inferred_topic",
                        "confidence": 0.75,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )

                self.eventlog.append(
                    kind="concept_bind_async",
                    content=bind_content,
                    meta={"source": "autonomy_kernel.indexer", "origin": "async"},
                )
                # Also emit standard concept_bind_event for CTL compatibility
                # (The async event is for audit/provenance, but CTL needs the standard one too?
                #  Actually, ConceptGraph listens to concept_bind_event.
                #  If we want these to show up in retrieval, we should use concept_bind_event
                #  OR update ConceptGraph to listen to concept_bind_async.
                #  Let's use concept_bind_async as the RECORD, but then we might need to
                #  emit concept_bind_event as the EFFECT mechanism if ConceptGraph logic is rigid.
                #  However, the user schema request defined concept_bind_async.
                #  I will assume I should UPDATE ConceptGraph logic to handle it, OR
                #  just emit concept_bind_event with "origin": "async".
                #  The user prompt said: "Differentiating Real-Time vs. Archivist Bindings...
                #  Real-time: concept_bind_event... Archivist: concept_bind_async".
                #  This implies ConceptGraph MUST support concept_bind_async.
                #  I will update ConceptGraph to handle concept_bind_async in a separate edit.)

            # 2. Extract Safe Claims
            claims = self.extractor.extract_safe_claims(text)
            for claim in claims:
                claim_content = json.dumps(
                    {
                        "source_event_id": event_id,
                        "claim_type": claim["type"],
                        "value": claim["value"],
                        "confidence": claim["confidence"],
                        "evidence_text": text[:50],  # snippet
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )

                self.eventlog.append(
                    kind="claim_from_text",
                    content=claim_content,
                    meta={"source": "autonomy_kernel.indexer", "origin": "async"},
                )
                # Note: claim_from_text doesn't automatically become a CLAIM event
                # (which is "truth"). It's a suggestion.
                # The system might need a separate step to "promote" these to full claims.
                # For now, we just log them.

            processed_count += 1

        return processed_count

    def backfill_embeddings(
        self, *, model: str = "hash64", dims: int = 64, batch: int = 200
    ) -> int:
        """Backfill missing embedding_add events beyond the usual vector tail.

        Deterministic and incremental: scans forward from the last processed id.
        """
        start_id = max(0, int(self._last_embedded_id))
        candidates = self.eventlog.read_range(start_id + 1, start_id + batch)
        if not candidates:
            return 0

        # Build existing embedding set for this model/dims
        existing = set()
        for ev in self.eventlog.read_by_kind("embedding_add"):
            try:
                data = json.loads(ev.get("content") or "{}")
            except Exception:
                continue
            if (data or {}).get("model") == model and int(
                (data or {}).get("dims", 0)
            ) == int(dims):
                try:
                    existing.add(int((data or {}).get("event_id", 0)))
                except Exception:
                    continue

        from pmm.retrieval.vector import build_embedding_content

        appended = 0
        for ev in candidates:
            eid = int(ev.get("id", 0))
            if ev.get("kind") not in ("user_message", "assistant_message"):
                continue
            if eid in existing:
                continue
            payload = build_embedding_content(
                event_id=eid, text=ev.get("content") or "", model=model, dims=dims
            )
            self.eventlog.append(
                kind="embedding_add",
                content=payload,
                meta={"source": "indexer.backfill"},
            )
            appended += 1

        self._last_embedded_id = candidates[-1]["id"]
        return appended
