#!/usr/bin/env python3
"""
Demo script for the new PMM Retrieval Pipeline (MemeGraph -> CTL -> Context).

This script:
1. Creates a fresh temporary EventLog.
2. Seeds the CTL Ontology (defines basic concepts).
3. Simulates a conversation where a user discusses a topic.
4. Prints the ACTUAL CONTEXT generated for the AI, showing the new sections.
"""

import json
import sys
import os

# Ensure we can import pmm
sys.path.insert(0, os.getcwd())

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop
from pmm.core.concept_ontology import seed_ctl_ontology


class VerboseAdapter:
    """A dummy adapter that prints the System Prompt (Context) it receives."""

    def __init__(self):
        self.turn_count = 0

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        self.turn_count += 1
        print("\n" + "=" * 80)
        print(f" [TURN {self.turn_count}] AI CONTEXT VIEW (What the LLM sees)")
        print("=" * 80)
        print(system_prompt)
        print("=" * 80 + "\n")

        # Simulate a response that creates a commitment, to trigger Thread logic
        return f"I acknowledge: {user_prompt}.\n\nCOMMIT: Process {user_prompt}"


def main():
    db_path = ".data/demo_pipeline.db"
    # Clean up old run
    if os.path.exists(db_path):
        os.remove(db_path)

    print(f"Initializing PMM on {db_path}...")
    log = EventLog(db_path)

    # 1. Initialize Loop (Seeds ontology automatically via ConceptGraph/Autonomy check usually,
    #    but let's do it explicitly to be sure for this short script)
    seed_ctl_ontology(log)

    # 2. Add a custom concept for our demo
    print("Seeding custom concepts...")
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "topic.neural_link",
                "concept_kind": "topic",
                "definition": "Direct interface between mind and machine.",
                "attributes": {},
                "version": "1",
            }
        ),
        meta={},
    )

    loop = RuntimeLoop(eventlog=log, adapter=VerboseAdapter(), autonomy=False)

    # 3. Turn 1: User mentions the concept.
    # We expect the pipeline to:
    # - Detect "topic.neural_link" (via keyword match in concept extraction?
    #   Actually, the current pipeline seeds from meta or config.
    #   Since we don't have a real Semantic Extractor running on USER input in this simple demo
    #   that puts tags in 'meta', we might need to force it or rely on Vector match if enabled.)
    #
    # Wait! The new pipeline in `loop.py` relies on `user_event` meta for seeding OR vector search.
    # If we want to see "Concepts" section, we need to ensure a concept is selected.
    # Vector search should pick up the previous definition/binding events if the text matches.

    print(">>> User says: 'Let's talk about the neural_link project.'")

    # We inject a hint in meta to simulate a "Smart" classifier for this demo
    # (In prod, this would come from an analyzer or previous turn context)
    # Actually, let's just rely on the fact that we just defined it, so vector might catch it?
    # Or we manually bind it to the user message for the demo.

    # Since run_turn appends the user message, we can't easily inject meta beforehand
    # unless we modify run_turn or just let it run.
    # Let's just run it. The context for THIS turn might not have it yet because it's generating reply TO this turn.
    # But the NEXT turn will definitely have it if we establish a thread.

    loop.run_turn("Let's talk about the neural_link project.")

    # 4. Turn 2: User continues.
    # Now we should have a thread established (COMMIT in turn 1).
    # And we want to bind the previous events to the concept to ensure they show up in Concept Context.

    # Manually bind previous user msg to concept (simulating async classification)
    events = log.read_all()
    last_user_msg = [e for e in events if e["kind"] == "user_message"][-1]
    log.append(
        kind="concept_bind_event",
        content=json.dumps(
            {
                "event_id": last_user_msg["id"],
                "tokens": ["topic.neural_link"],
                "relation": "discusses",
            }
        ),
        meta={},
    )

    print(">>> User says: 'What is the status?'")
    loop.run_turn("What is the status?")


if __name__ == "__main__":
    main()
