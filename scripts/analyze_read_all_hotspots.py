#!/usr/bin/env python3
"""Analyze read_all() call patterns in the codebase.

After the monolithic refactor, performance degraded. This script identifies
where read_all() is being called excessively.
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


class ReadAllVisitor(ast.NodeVisitor):
    """AST visitor to find read_all() calls."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.calls = []
        self.current_function = None
        self.current_class = None

    def visit_ClassDef(self, node):
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    def visit_Call(self, node):
        # Check for .read_all() calls
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "read_all":
                location = f"{self.filepath.name}"
                if self.current_class:
                    location += f"::{self.current_class}"
                if self.current_function:
                    location += f"::{self.current_function}"
                location += f":L{node.lineno}"

                self.calls.append(
                    {
                        "location": location,
                        "line": node.lineno,
                        "function": self.current_function,
                        "class": self.current_class,
                    }
                )

        self.generic_visit(node)


def analyze_file(filepath: Path) -> list[dict[str, Any]]:
    """Analyze a single Python file for read_all() calls."""
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=str(filepath))
        visitor = ReadAllVisitor(filepath)
        visitor.visit(tree)
        return visitor.calls
    except Exception as e:
        print(f"Error analyzing {filepath}: {e}", file=sys.stderr)
        return []


def analyze_directory(directory: Path, pattern: str = "*.py") -> dict[str, list[dict]]:
    """Analyze all Python files in a directory."""
    results = {}

    for filepath in directory.rglob(pattern):
        # Skip test files and __pycache__
        if "__pycache__" in str(filepath) or "test_" in filepath.name:
            continue

        calls = analyze_file(filepath)
        if calls:
            results[str(filepath.relative_to(directory.parent))] = calls

    return results


def print_hotspot_report(results: dict[str, list[dict]]):
    """Print a report of read_all() hotspots."""
    print("=" * 80)
    print("READ_ALL() HOTSPOT ANALYSIS")
    print("=" * 80)
    print()

    # Count by file
    file_counts = {filepath: len(calls) for filepath, calls in results.items()}
    sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)

    print("## Files with Most read_all() Calls")
    print("-" * 80)
    total_calls = sum(file_counts.values())
    print(f"Total read_all() calls found: {total_calls}")
    print()

    for filepath, count in sorted_files[:20]:  # Top 20
        print(f"{count:3d}  {filepath}")

    print()
    print("## Detailed Hotspots (Top 10 Files)")
    print("-" * 80)

    for filepath, count in sorted_files[:10]:
        print(f"\n### {filepath} ({count} calls)")
        calls = results[filepath]

        # Group by function
        by_function = defaultdict(list)
        for call in calls:
            func_name = call["function"] or "<module>"
            by_function[func_name].append(call)

        for func_name, func_calls in sorted(
            by_function.items(), key=lambda x: len(x[1]), reverse=True
        ):
            lines = [str(c["line"]) for c in func_calls]
            print(f"  {func_name}: {len(func_calls)} calls (lines: {', '.join(lines)})")

    print()
    print("## Critical Patterns")
    print("-" * 80)

    # Identify functions with multiple read_all() calls
    multi_call_functions = []
    for filepath, calls in results.items():
        by_function = defaultdict(list)
        for call in calls:
            func_key = (
                f"{filepath}::{call['class'] or ''}.{call['function'] or '<module>'}"
            )
            by_function[func_key].append(call)

        for func_key, func_calls in by_function.items():
            if len(func_calls) > 1:
                multi_call_functions.append((func_key, len(func_calls)))

    multi_call_functions.sort(key=lambda x: x[1], reverse=True)

    print("Functions with multiple read_all() calls (likely bottlenecks):")
    print()
    for func_key, count in multi_call_functions[:15]:
        print(f"  {count}x  {func_key}")

    print()
    print("## Recommendations")
    print("=" * 80)
    print(
        """
1. **Pass events as parameters**: Instead of calling read_all() in every function,
   pass the events list as a parameter from the caller.

2. **Use request-scoped caching**: Implement a RequestCache that caches read_all()
   results for the duration of a single operation.

3. **Use read_tail() for recent data**: Many operations only need recent events.
   Use read_tail(limit=N) instead of read_all().

4. **Batch operations**: If multiple functions need events, call read_all() once
   at the top level and pass the result down.

5. **Leverage snapshot cache**: Use Runtime._get_snapshot() which caches the
   projection until new events are appended.

6. **Profile before/after**: Use scripts/profile_performance.py to measure
   the impact of optimizations.
"""
    )


def main():
    """Main entry point."""
    project_root = Path(__file__).parent.parent

    # Analyze key directories
    print("Analyzing codebase for read_all() calls...")
    print()

    results = {}

    # Analyze pmm/runtime
    runtime_results = analyze_directory(project_root / "pmm" / "runtime")
    results.update(runtime_results)

    # Analyze pmm/commitments
    commitments_results = analyze_directory(project_root / "pmm" / "commitments")
    results.update(commitments_results)

    # Print report
    print_hotspot_report(results)


if __name__ == "__main__":
    main()
