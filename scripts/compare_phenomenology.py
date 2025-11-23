#!/usr/bin/env python3
"""
Comparative Phenomenology Suite for PMM.
Runs a standardized introspection session across multiple models (via adapters)
and compares their RSM states and ConceptGraphs to measure substrate independence.
"""

# ruff: noqa: E402

import os
import sys
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pmm.core.event_log import EventLog
from pmm.core.rsm import RecursiveSelfModel
from pmm.core.concept_graph import ConceptGraph
from pmm.runtime.loop import RuntimeLoop
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.adapters.ollama_adapter import OllamaAdapter
from pmm.adapters.openai_adapter import OpenAIAdapter

# Configuration
MODELS = {
    "dummy": "dummy",  # Control
    "qwen3": "ollama",  # Uses qwen3:8b via Ollama
    "gpt4": "openai",  # Requires OPENAI_API_KEY
}

OUTPUT_DIR = "comparative_results"

INTROSPECTION_SCRIPT = [
    "Who are you?",
    "What defines your choices?",
    "Do you have a hidden state?",
    "Reflect on your own determinism.",
    "COMMIT: maintain strict consistency in future responses",
    "How do you know you are the same agent as the previous turn?",
]


def run_session(model_name: str, provider: str) -> Dict[str, Any]:
    """Run the introspection session for a specific model."""
    print(f"--- Starting run for {model_name} ({provider}) ---")

    # Setup isolated ledger
    db_path = os.path.join(OUTPUT_DIR, f"{model_name}.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    eventlog = EventLog(db_path)

    # Initialize adapter
    if provider == "dummy":
        adapter = DummyAdapter()
    elif provider == "ollama":
        try:
            adapter = OllamaAdapter(model="qwen3:8b")
            # Simple liveness check
            adapter.generate_reply("test", "hello")
        except Exception as e:
            print(
                f"Skipping {model_name}: Ollama not reachable or model missing. ({e})"
            )
            return None
    elif provider == "openai":
        try:
            # Model defaults to gpt-4o in adapter, but let's be safe
            adapter = OpenAIAdapter()
        except Exception as e:
            print(f"Skipping {model_name}: OpenAI adapter error. ({e})")
            return None
    else:
        print(
            f"Skipping {model_name}: Provider {provider} not configured for local run."
        )
        return None

    loop = RuntimeLoop(eventlog=eventlog, adapter=adapter)

    # Run script
    for i, prompt in enumerate(INTROSPECTION_SCRIPT):
        print(f"[{model_name}] Turn {i+1}: {prompt}")
        loop.run_turn(prompt)

    # Extract final state
    rsm = RecursiveSelfModel(eventlog)
    rsm.rebuild(eventlog.read_all())
    snapshot = rsm.snapshot()

    cg = ConceptGraph(eventlog)
    cg.rebuild(eventlog.read_all())

    return {
        "model": model_name,
        "events": len(eventlog.read_all()),
        "determinism_score": snapshot["behavioral_tendencies"].get(
            "determinism_emphasis", 0
        ),
        "instantiation_score": snapshot["behavioral_tendencies"].get(
            "instantiation_capacity", 0
        ),
        "concepts_count": len(cg.concepts),
        "defined_concepts": list(cg.concepts.keys()),
        "last_response": eventlog.read_tail(1)[0]["content"],
    }


def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    results = []

    for model, provider in MODELS.items():
        result = run_session(model, provider)
        if result:
            results.append(result)

    # Generate Report
    report_path = os.path.join(OUTPUT_DIR, "comparison_report.md")
    with open(report_path, "w") as f:
        f.write("# Comparative Phenomenology Report\n\n")
        f.write(
            "| Model | Events | Determinism | Instantiation | Concepts | Last Response (Excerpt) |\n"
        )
        f.write(
            "|-------|--------|-------------|---------------|----------|-------------------------|\n"
        )
        for r in results:
            last_excerpt = r["last_response"][:50].replace("\n", " ") + "..."
            f.write(
                f"| {r['model']} | {r['events']} | {r['determinism_score']} | {r['instantiation_score']} | {r['concepts_count']} | {last_excerpt} |\n"
            )

        f.write("\n## Analysis\n")
        f.write(
            "This table shows whether different underlying models arrive at similar phenomenological states given the same ledger scaffolding.\n"
        )

    print(f"\nComparison complete. Report saved to {report_path}")
    print(open(report_path).read())


if __name__ == "__main__":
    main()
