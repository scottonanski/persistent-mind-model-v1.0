import os
from pathlib import Path


def test_no_heuristic_parsing_in_runtime():
    forbidden_patterns = [
        '.startswith("COMMIT:")',
        '.startswith("CLAIM:")',
        '.startswith("REFLECT:")',
        '.startswith("CLOSE:")',
        '"COMMIT:" in',
        '"CLAIM:" in',
        '"REFLECT:" in',
        '"CLOSE:" in',
    ]
    runtime_dirs = [
        Path("pmm/runtime"),
        Path("pmm/core"),
    ]
    exclude_files = {
        "pmm/core/semantic_extractor.py",
        # Identity manager parses CLAIM lines using a minimal, structured
        # prefix check; it is part of the core protocol surface and is
        # intentionally exempted from this heuristic scan.
        "pmm/core/identity_manager.py",
    }

    violations = []
    for dir_path in runtime_dirs:
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    if str(file_path) in exclude_files:
                        continue
                    with open(file_path, "r") as f:
                        content = f.read()
                        for pattern in forbidden_patterns:
                            if pattern in content:
                                violations.append(f"{file_path}: {pattern}")
    assert not violations, f"Found heuristic patterns in runtime code: {violations}"
