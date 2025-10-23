from __future__ import annotations
import os, re
import importlib


def test_cadence_defined_once_and_in_loop():
    loop = importlib.import_module("pmm.runtime.loop")
    table = getattr(loop, "CADENCE_BY_STAGE", None)
    assert isinstance(table, dict) and len(table) > 0, (
        "CADENCE_BY_STAGE must be a non-empty dict on pmm.runtime.loop"
    )

    root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pmm", "runtime")
    pattern = re.compile(r"^\s*CADENCE_BY_STAGE\s*=")
    offenders: list[str] = []
    for base, _dirs, files in os.walk(root):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(base, fname)
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh, 1):
                    if pattern.search(line):
                        if not path.endswith(os.path.join("runtime", "loop.py")):
                            offenders.append(f"{path}:{i}")
    assert not offenders, f"Duplicate CADENCE_BY_STAGE definitions found in: {offenders}"
