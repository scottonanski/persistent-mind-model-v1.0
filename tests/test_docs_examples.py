import json
import subprocess

import pytest


def test_api_example_snapshot_ok():
    # Quick health check: skip if local API server isn't running
    check = subprocess.run(
        ["curl", "-s", "http://127.0.0.1:8000/snapshot?db=:memory:"],
        text=True,
        capture_output=True,
    )
    if check.returncode != 0 or not (check.stdout or "").strip():
        pytest.skip(
            "API server not running on 127.0.0.1:8000; skipping docs example test"
        )

    # mirrors the docs example: GET /snapshot
    out = subprocess.check_output(
        ["curl", "-s", "http://127.0.0.1:8000/snapshot?db=.data/pmm.db"],
        text=True,
    )
    data = json.loads(out)
    # assert minimal, stable fields used in docs
    assert "identity" in data
    assert "events" in data
    assert "directives" in data
