# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_concept_graph_async.py
"""Deterministic unit test for async concept bindings in ConceptGraph."""

import json
import unittest
from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph


class TestConceptGraphAsync(unittest.TestCase):
    def test_concept_bind_async_processing(self):
        """Verify that concept_bind_async is correctly processed by ConceptGraph."""
        log = EventLog(":memory:")

        # 1. Create a user message
        user_msg_id = log.append(
            kind="user_message",
            content="I think I might buy a cat.",
            meta={"role": "user"},
        )

        # 2. Define the concept (usually handled by seed/define, mimicking that)
        log.append(
            kind="concept_define",
            content=json.dumps(
                {
                    "token": "topic.animals.cats",
                    "concept_kind": "topic",
                    "definition": "Feline animals.",
                    "version": 1,
                }
            ),
            meta={"concept_id": "c_cats"},
        )

        # 3. Create an async binding event (as if from Indexer)
        async_bind_content = json.dumps(
            {
                "event_id": user_msg_id,
                "tokens": ["topic.animals.cats"],
                "relation": "inferred_topic",
                "confidence": 0.75,
            }
        )

        log.append(
            kind="concept_bind_async",
            content=async_bind_content,
            meta={"source": "autonomy_kernel.indexer", "origin": "async"},
        )

        # 4. Initialize ConceptGraph and Rebuild
        cg = ConceptGraph(log)
        cg.rebuild()

        # 5. Assertions

        # Verify events_for_concept
        events = cg.events_for_concept("topic.animals.cats")
        self.assertIn(user_msg_id, events, "Async binding should link concept to event")

        # Verify concepts_for_event
        concepts = cg.concepts_for_event(user_msg_id)
        self.assertIn(
            "topic.animals.cats",
            concepts,
            "Event should be linked to concept via async binding",
        )

        # Verify relation tracking (optional but good to check)
        # Accessing internal set for verification
        relation_found = False
        for token, eid, rel in cg.event_binding_relations:
            if (
                token == "topic.animals.cats"
                and eid == user_msg_id
                and rel == "inferred_topic"
            ):
                relation_found = True
                break
        self.assertTrue(relation_found, "Binding relation should be tracked correctly")

        print(
            "\n✅ Test Passed: Async concept bindings are fully integrated into ConceptGraph."
        )


if __name__ == "__main__":
    unittest.main()
