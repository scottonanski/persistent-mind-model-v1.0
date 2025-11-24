# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: scripts/binding_audit.py
"""
Audit and optionally backfill CTL bindings for claim events in a ledger.

Usage:
    python3 scripts/binding_audit.py --db pmm.db --mode audit
    python3 scripts/binding_audit.py --db pmm.db --mode backfill
"""

from __future__ import annotations

import argparse
from typing import List

from pmm.core.event_log import EventLog
from pmm.tools.binding_audit import audit_bindings, backfill_bindings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit/backfill CTL bindings for claim events."
    )
    parser.add_argument(
        "--db",
        default="pmm.db",
        help="Path to the ledger SQLite file (default: pmm.db)",
    )
    parser.add_argument(
        "--mode",
        choices=["audit", "backfill"],
        default="audit",
        help="Audit only or apply backfill for missing bindings.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    elog = EventLog(args.db)

    gaps = audit_bindings(elog)
    if args.mode == "audit":
        if not gaps:
            print("No missing bindings detected.")
            return
        print("Missing bindings:")
        for gap in gaps:
            print(f"- event_id={gap.event_id} token={gap.token} reason={gap.reason}")
        return

    # backfill mode
    appended: List[int] = backfill_bindings(elog, gaps)
    print(f"Found {len(gaps)} gaps; appended {len(appended)} concept_bind_event rows.")


if __name__ == "__main__":
    main()
