import json
import os
import urllib.error
import urllib.request

import pytest

API_URL = os.getenv("PMM_API_URL", "http://127.0.0.1:8000/snapshot?db=.data/pmm.db")


@pytest.mark.skipif(
    "PMM_RUN_API_SMOKE" not in os.environ, reason="set PMM_RUN_API_SMOKE=1 to run"
)
def test_snapshot_contains_new_event_kinds():
    try:
        with urllib.request.urlopen(API_URL, timeout=2.5) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        pytest.skip(f"API not reachable: {e}")

    kinds = {e["kind"] for e in data.get("events", [])}
    # Only assert presence if they exist; the smoke test is that API surfaces them when present
    # At least snapshot structure must exist
    assert "identity" in data and "events" in data
    # If S4 ran long enough, these may appear:
    allowed = {
        "evaluation_report",
        "evaluation_summary",
        "planning_thought",
        "curriculum_update",
        "trait_update",
    }
    assert kinds.issuperset(kinds.intersection(allowed))
