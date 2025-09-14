import json
import subprocess


def test_api_example_snapshot_ok():
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
