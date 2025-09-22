#!/usr/bin/env python3
"""Debug script to test IAS/GAS computation on current database."""

import sys
import os

sys.path.insert(
    0, "/home/scott/Documents/Projects/Business-Development/persistent-mind-model"
)

from pmm.storage.eventlog import EventLog
from pmm.runtime.metrics import (
    compute_ias_gas,
    get_or_compute_ias_gas,
    diagnose_ias_calculation,
)
from pmm.runtime.stage_tracker import StageTracker


def main():
    # Load the database
    db_path = "/home/scott/Documents/Projects/Business-Development/persistent-mind-model/.data/pmm.db"

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    eventlog = EventLog(path=db_path)

    print("=== Database Analysis ===")

    # Get all events
    events = eventlog.read_all()
    print(f"Total events: {len(events)}")

    # Count event types
    event_counts = {}
    for event in events:
        kind = event.get("kind", "unknown")
        event_counts[kind] = event_counts.get(kind, 0) + 1

    print("Event counts:")
    for kind, count in sorted(event_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {kind}: {count}")

    # Count autonomy ticks
    autonomy_ticks = [e for e in events if e.get("kind") == "autonomy_tick"]
    print(f"Autonomy ticks: {len(autonomy_ticks)}")

    # Count identity adopts
    identity_adopts = [e for e in events if e.get("kind") == "identity_adopt"]
    print(f"Identity adopts: {len(identity_adopts)}")

    for adopt in identity_adopts:
        print(
            f"  - ID {adopt.get('id')}: {adopt.get('content')} (meta: {adopt.get('meta', {})})"
        )

    # Compute metrics
    print("\n=== Metrics Computation ===")
    try:
        ias, gas = compute_ias_gas(events)
        print(f"compute_ias_gas result: IAS={ias}, GAS={gas}")
    except Exception as e:
        print(f"Error in compute_ias_gas: {e}")
        import traceback

        traceback.print_exc()

    # Try get_or_compute_ias_gas
    try:
        ias2, gas2 = get_or_compute_ias_gas(eventlog)
        print(f"get_or_compute_ias_gas result: IAS={ias2}, GAS={gas2}")
    except Exception as e:
        print(f"Error in get_or_compute_ias_gas: {e}")
        import traceback

        traceback.print_exc()

    # Diagnose IAS calculation
    print("\n=== IAS Diagnosis ===")
    try:
        diagnosis = diagnose_ias_calculation(events)
        print("Diagnosis result:")
        for key, value in diagnosis.items():
            print(f"  {key}: {value}")
    except Exception as e:
        print(f"Error in diagnose_ias_calculation: {e}")
        import traceback

        traceback.print_exc()

    # Check stage
    print("\n=== Stage Analysis ===")
    try:
        stage, snapshot = StageTracker.infer_stage(events)
        print(f"Current stage: {stage}")
        print(f"Stage snapshot: {snapshot}")
    except Exception as e:
        print(f"Error in StageTracker.infer_stage: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
