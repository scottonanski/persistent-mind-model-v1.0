from __future__ import annotations
import os, re

ROOT = os.path.dirname(os.path.dirname(__file__))
PATTERN = re.compile(r"traits\.[A-Z]")  # any uppercase after 'traits.'

def _iter_py_files():
    for base, _dirs, files in os.walk(os.path.join(ROOT, "pmm")):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)

def test_no_uppercase_traits_keys_in_code():
    offenders = []
    for path in _iter_py_files():
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            txt = fh.read()
        # ignore tests and migrations if you ever add them under pmm/
        if "/tests/" in path or "/migration/" in path:
            continue
        if PATTERN.search(txt):
            offenders.append(path)
    assert not offenders, f"Uppercase 'traits.*' found in: {offenders}"
