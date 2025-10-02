#!/usr/bin/env python3
"""Phase 3: Quick GPU Verification

Simple script to verify GPU acceleration is working with PMM.
Model-agnostic - works with any Ollama model.
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog


def check_gpu_available():
    """Check if GPU is detected."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            gpu_info = result.stdout.strip()
            print(f"✓ GPU detected: {gpu_info}")
            return True
        return False
    except Exception:
        return False


def test_pmm_streaming():
    """Quick test of PMM streaming with GPU."""
    print("\nTesting PMM with GPU acceleration...")
    print("-" * 60)

    # Get first available model
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    lines = result.stdout.strip().split("\n")[1:]  # Skip header

    if not lines:
        print("✗ No Ollama models found. Please install a model first:")
        print("  ollama pull llama3.2:3b")
        return False

    # Use first model
    model = lines[0].split()[0]
    print(f"Using model: {model}")

    # Setup PMM
    db_path = ".data/gpu_test.db"
    eventlog = EventLog(db_path)
    config = LLMConfig(provider="ollama", model=model)
    runtime = Runtime(config, eventlog)

    # Test query
    query = "Say 'GPU test successful' and nothing else"
    print(f"Query: {query}")
    print("\nResponse: ", end="", flush=True)

    start = time.time()
    first_token_time = None
    token_count = 0

    try:
        for token in runtime.handle_user_stream(query):
            if first_token_time is None:
                first_token_time = time.time() - start
            print(token, end="", flush=True)
            token_count += 1

        total_time = time.time() - start
        print("\n\n✓ Streaming successful!")
        print(f"  Time to first token: {first_token_time*1000:.0f}ms")
        print(f"  Total time: {total_time*1000:.0f}ms")
        print(f"  Tokens: {token_count}")

        if token_count > 0:
            tok_per_sec = token_count / total_time
            print(f"  Speed: {tok_per_sec:.1f} tok/s")

            # Check if GPU speed (>20 tok/s indicates GPU)
            if tok_per_sec > 20:
                print("\n✓ GPU acceleration confirmed! (Speed indicates GPU usage)")
                return True
            else:
                print("\n⚠ Speed seems slow - may be using CPU")
                print("  Check: watch -n 1 nvidia-smi")
                return False

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("Phase 3: GPU Acceleration Verification")
    print("=" * 60)
    print()

    # Check GPU
    if not check_gpu_available():
        print("✗ No GPU detected")
        print("  Make sure NVIDIA drivers are installed")
        return 1

    # Test PMM
    if not test_pmm_streaming():
        print("\n✗ GPU verification failed")
        return 1

    print("\n" + "=" * 60)
    print("✓ Phase 3 GPU Acceleration: VERIFIED")
    print("=" * 60)
    print()
    print("GPU is working with PMM!")
    print()
    print("Next: Stage 3 - Database Indexing")
    print("  This will speed up database queries for ALL models")
    print()
    print("To proceed:")
    print("  python scripts/phase3_stage3_db_indexing.py")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
