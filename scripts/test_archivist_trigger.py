# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: scripts/test_archivist_trigger.py
"""Deterministic reproduction script for forcing the Archivist Indexer to run.

This script:
1. Initializes a memory-based EventLog with no prior history.
2. Injects a user message *without* triggering a model response or active indexing.
3. Forces an AutonomyKernel decision cycle.
4. Verifies that decision='index' is produced.
5. Runs the loop tick to execute the decision.
6. Asserts that concept_bind_async events are created.
"""

import json
import sys

# Ensure project root is in path
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop
from pmm.core.concept_graph import ConceptGraph


# Mock adapter just to satisfy RuntimeLoop init (though we won't run a chat turn)
class DummyAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return ""


def main():
    print("🛠️  Initializing Archivist Trigger Test...")

    # 1. Setup clean ledger
    log = EventLog(":memory:", mode="writer", writer_role="archivist-trigger-test")

    # Inject config to ensure kernel behaves predictably
    log.append(
        kind="config",
        content=json.dumps(
            {
                "type": "autonomy_thresholds",
                "reflection_interval": 10,
                "summary_interval": 50,
            }
        ),
        meta={"source": "test"},
    )

    # 2. Inject User Messages (UNINDEXED)
    # We intentionally make them long enough to be 'interesting' but simple enough to parse.
    # "I love programming in Python on Linux." -> should trigger 'topic.programming.python', 'topic.os.linux'
    user_msg_1 = log.append(
        kind="user_message",
        content="I love programming in Python on Linux.",
        meta={"role": "user"},
    )
    # Inject a second message to satisfy the >= 2 unindexed threshold
    user_msg_2 = log.append(
        kind="user_message", content="My name is Scott.", meta={"role": "user"}
    )
    print(f"📝 Injected User Messages ({user_msg_1}, {user_msg_2})")

    # Inject a metrics_turn to satisfy kernel safety check
    log.append(kind="metrics_turn", content="lat_ms:10", meta={})
    print("⏱️  Injected metrics_turn")

    # 3. Initialize Runtime Components
    adapter = DummyAdapter()
    loop = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=True)

    # Manually set tick counter to satisfy the "idle gap" constraint
    # The kernel requires > 4 ticks since last index.
    # We can force this by manipulating the kernel state directly for the test.
    loop.autonomy.ticks_since_last_index = 10
    print(f"⏱️  Forced ticks_since_last_index = {loop.autonomy.ticks_since_last_index}")

    # 4. Force Decision
    print("🤖 Invoking AutonomyKernel.decide_next_action()...")
    decision = loop.autonomy.decide_next_action()
    print(f"🔍 Decision: {decision.decision}")
    print(f"   Reasoning: {decision.reasoning}")

    if decision.decision != "index":
        print("❌ FAILED: Kernel did not decide to index.")
        # Debug info
        print("   ConceptGraph Coverage:")
        for mid in (user_msg_1, user_msg_2):
            concepts = loop.concept_graph.concepts_for_event(mid)
            print(f"   - Event {mid} concepts: {concepts}")
        sys.exit(1)

    # 5. Run Tick to Execute
    print("🚀 Executing RuntimeLoop.run_tick()...")
    loop.run_tick(slot=1, slot_id="test_slot")

    # 6. Verify Outcome
    print("🔎 Verifying Ledger for Archivist events...")
    all_events = log.read_all()

    async_binds = [e for e in all_events if e["kind"] == "concept_bind_async"]
    async_claims = [e for e in all_events if e["kind"] == "claim_from_text"]

    if not async_binds and not async_claims:
        print("❌ FAILED: No async events produced.")
        sys.exit(1)

    print(
        f"✅ SUCCESS: Found {len(async_binds)} async bindings and {len(async_claims)} async claims."
    )

    for e in async_binds:
        print(f"   - Async Bind: {e['content']}")

    for e in async_claims:
        print(f"   - Async Claim: {e['content']}")

    # 7. Verify ConceptGraph Integration
    # Rebuild graph to be sure
    cg = ConceptGraph(log)
    cg.rebuild()

    tokens_1 = cg.concepts_for_event(user_msg_1)
    print(f"🧠 ConceptGraph tokens for event {user_msg_1}: {tokens_1}")

    tokens_2 = cg.concepts_for_event(user_msg_2)
    print(f"🧠 ConceptGraph tokens for event {user_msg_2}: {tokens_2}")

    expected_tokens = {"topic.programming.python", "topic.os.linux"}
    if expected_tokens.intersection(set(tokens_1)):
        print("✅ ConceptGraph correctly indexed the async tags.")
    else:
        print("❌ ConceptGraph missing expected tokens.")
        sys.exit(1)
    log.close()


if __name__ == "__main__":
    main()
