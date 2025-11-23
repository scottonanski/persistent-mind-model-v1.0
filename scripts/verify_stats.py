import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph


def check_db(name: str):
    db_path = f"comparative_results/{name}.db"
    if not os.path.exists(db_path):
        print(f"{name}: DB not found")
        return

    log = EventLog(db_path)
    events = log.read_all()
    cg = ConceptGraph(log)
    cg.rebuild(events)

    print(f"{name}: {len(events)} events, {len(cg.concepts)} concepts")


if __name__ == "__main__":
    check_db("dummy")
    check_db("qwen3")
    check_db("gpt4")
