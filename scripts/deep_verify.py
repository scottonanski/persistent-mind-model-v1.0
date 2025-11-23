import sys
import os
import json
from collections import Counter

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pmm.core.event_log import EventLog


def analyze_db(name: str):
    db_path = f"comparative_results/{name}.db"
    if not os.path.exists(db_path):
        print(f"{name}: DB not found")
        return

    print(f"\n--- Analysis: {name} ---")
    log = EventLog(db_path)
    events = log.read_all()

    # 1. Event Kind Distribution
    kinds = [e["kind"] for e in events]
    counts = Counter(kinds)
    print("Event Counts:")
    for k, v in sorted(counts.items()):
        if k in [
            "commitment_close",
            "reflection",
            "stability_metrics",
            "concept_define",
        ]:
            print(f"  {k}: {v}")

    # 2. RSM State from last summary
    summaries = [e for e in events if e["kind"] == "summary_update"]
    if summaries:
        last_sum = summaries[-1]
        meta = last_sum.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                pass

        rsm = meta.get("rsm_state", {}).get("behavioral_tendencies", {})
        print(f"Final RSM State: {rsm}")
    else:
        print("Final RSM State: None found")


if __name__ == "__main__":
    analyze_db("dummy")
    analyze_db("qwen3")
    analyze_db("gpt4")
