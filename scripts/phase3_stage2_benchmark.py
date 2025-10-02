#!/usr/bin/env python3
"""Phase 3 Stage 2: GPU Performance Benchmarking

Measures actual GPU speedup and PMM performance improvements.
"""

import subprocess
import sys
import time
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime
from pmm.storage.eventlog import EventLog


def run_ollama_query(model: str, prompt: str, timeout: int = 60) -> tuple[float, str]:
    """Run a query through Ollama and measure time."""
    start = time.time()
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start
        return duration, result.stdout
    except subprocess.TimeoutExpired:
        return timeout, "TIMEOUT"
    except Exception as e:
        return -1, f"ERROR: {e}"


def estimate_tokens(text: str) -> int:
    """Rough token estimate (words * 1.3)."""
    return int(len(text.split()) * 1.3)


def benchmark_ollama_direct(model: str, runs: int = 3):
    """Benchmark Ollama directly (without PMM)."""
    print(f"\n{'='*60}")
    print(f"Benchmarking Ollama Direct: {model}")
    print(f"{'='*60}\n")

    queries = [
        ("Short", "What is 2+2?"),
        ("Medium", "Explain what a neural network is in one paragraph."),
        ("Long", "Count from 1 to 50"),
    ]

    results = {}

    for name, query in queries:
        print(f"\n{name} query: '{query[:50]}...'")
        times = []
        token_counts = []

        for i in range(runs):
            duration, output = run_ollama_query(model, query)
            if duration > 0:
                tokens = estimate_tokens(output)
                times.append(duration)
                token_counts.append(tokens)
                tok_per_sec = tokens / duration if duration > 0 else 0
                print(
                    f"  Run {i+1}: {duration:.2f}s ({tokens} tokens, {tok_per_sec:.1f} tok/s)"
                )
            else:
                print(f"  Run {i+1}: FAILED")

        if times:
            avg_time = sum(times) / len(times)
            avg_tokens = sum(token_counts) / len(token_counts)
            avg_tok_per_sec = avg_tokens / avg_time

            results[name] = {
                "time": avg_time,
                "tokens": avg_tokens,
                "tok_per_sec": avg_tok_per_sec,
            }

            print(f"  Average: {avg_time:.2f}s ({avg_tok_per_sec:.1f} tok/s)")

    return results


def benchmark_pmm_streaming(model: str, runs: int = 3):
    """Benchmark PMM with streaming."""
    print(f"\n{'='*60}")
    print(f"Benchmarking PMM with Streaming: {model}")
    print(f"{'='*60}\n")

    # Setup
    db_path = ".data/phase3_benchmark.db"
    eventlog = EventLog(db_path)
    config = LLMConfig(provider="ollama", model=model)
    runtime = Runtime(config, eventlog)

    queries = [
        ("Short", "What is 2+2?"),
        ("Medium", "Explain what a neural network is in one paragraph."),
        ("Long", "Count from 1 to 50"),
    ]

    results = {}

    for name, query in queries:
        print(f"\n{name} query: '{query[:50]}...'")
        times = []
        first_token_times = []
        token_counts = []

        for i in range(runs):
            start = time.time()
            first_token_time = None
            tokens = []

            try:
                for token in runtime.handle_user_stream(query):
                    if first_token_time is None:
                        first_token_time = time.time() - start
                    tokens.append(token)

                duration = time.time() - start
                times.append(duration)
                first_token_times.append(first_token_time)
                token_counts.append(len(tokens))

                tok_per_sec = len(tokens) / duration if duration > 0 else 0
                print(
                    f"  Run {i+1}: {duration:.2f}s (first token: {first_token_time*1000:.0f}ms, {tok_per_sec:.1f} tok/s)"
                )

            except Exception as e:
                print(f"  Run {i+1}: FAILED - {e}")

        if times:
            avg_time = sum(times) / len(times)
            avg_first_token = sum(first_token_times) / len(first_token_times)
            avg_tokens = sum(token_counts) / len(token_counts)
            avg_tok_per_sec = avg_tokens / avg_time

            results[name] = {
                "time": avg_time,
                "first_token_ms": avg_first_token * 1000,
                "tokens": avg_tokens,
                "tok_per_sec": avg_tok_per_sec,
            }

            print(
                f"  Average: {avg_time:.2f}s (first token: {avg_first_token*1000:.0f}ms, {avg_tok_per_sec:.1f} tok/s)"
            )

    return results


def print_summary(ollama_results: dict, pmm_results: dict):
    """Print comparison summary."""
    print(f"\n{'='*60}")
    print("SUMMARY: GPU Performance")
    print(f"{'='*60}\n")

    print(f"{'Query':<12} {'Ollama':<15} {'PMM':<15} {'First Token':<15}")
    print(f"{'-'*60}")

    for name in ollama_results.keys():
        ollama = ollama_results[name]
        pmm = pmm_results[name]

        ollama_time = f"{ollama['time']:.2f}s"
        pmm_time = f"{pmm['time']:.2f}s"
        first_token = f"{pmm['first_token_ms']:.0f}ms"

        print(f"{name:<12} {ollama_time:<15} {pmm_time:<15} {first_token:<15}")

    print(f"\n{'='*60}")
    print("Tokens per Second")
    print(f"{'='*60}\n")

    for name in ollama_results.keys():
        ollama = ollama_results[name]
        pmm = pmm_results[name]

        print(
            f"{name:<12} Ollama: {ollama['tok_per_sec']:.1f} tok/s  |  PMM: {pmm['tok_per_sec']:.1f} tok/s"
        )

    # Calculate average speedup
    avg_ollama_tok = sum(r["tok_per_sec"] for r in ollama_results.values()) / len(
        ollama_results
    )
    avg_pmm_tok = sum(r["tok_per_sec"] for r in pmm_results.values()) / len(pmm_results)

    print(f"\n{'='*60}")
    print("Average Performance:")
    print(f"  Ollama: {avg_ollama_tok:.1f} tok/s")
    print(f"  PMM:    {avg_pmm_tok:.1f} tok/s")
    print(f"{'='*60}\n")

    # Estimate CPU baseline (from Phase 2.1 analysis)
    cpu_baseline_tok = 12  # tokens/sec on CPU
    gpu_speedup = avg_pmm_tok / cpu_baseline_tok

    print(f"Estimated GPU Speedup: {gpu_speedup:.1f}x faster than CPU")
    print(f"  (CPU baseline: ~{cpu_baseline_tok} tok/s)")
    print(f"  (GPU actual: ~{avg_pmm_tok:.1f} tok/s)")
    print()


def main():
    """Run Phase 3 Stage 2 benchmarks."""
    print("=" * 60)
    print("Phase 3 Stage 2: GPU Performance Benchmark")
    print("=" * 60)
    print()

    # Detect available model
    print("Detecting installed models...")
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    print(result.stdout)

    # Ask user which model to benchmark
    model = input("\nEnter model name to benchmark (e.g., gemma3:4b-it-qat): ").strip()

    if not model:
        print("No model specified. Exiting.")
        return

    print(f"\nBenchmarking with model: {model}")
    print("This will take ~5 minutes...")
    print()

    # Run benchmarks
    ollama_results = benchmark_ollama_direct(model, runs=3)
    pmm_results = benchmark_pmm_streaming(model, runs=3)

    # Print summary
    print_summary(ollama_results, pmm_results)

    print("\n✓ Benchmark complete!")
    print("\nNext steps:")
    print("  1. Check GPU utilization: watch -n 1 nvidia-smi")
    print("  2. Test PMM CLI: python -m pmm.cli.chat")
    print("  3. Run Stage 3: Database indexing")
    print()


if __name__ == "__main__":
    main()
