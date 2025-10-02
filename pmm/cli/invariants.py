from __future__ import annotations

import argparse

from pmm.runtime.invariants import check_invariants
from pmm.storage.eventlog import EventLog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PMM invariants checker")
    parser.add_argument(
        "--db",
        help="Path to SQLite event log (default: .data/pmm.db)",
        default=".data/pmm.db",
    )
    args = parser.parse_args(argv)

    log = EventLog(args.db)
    events = log.read_all()
    violations = check_invariants(events)

    if not violations:
        print("OK: no invariant violations found (", len(events), "events)")
        return 0

    print("Invariant violations (", len(violations), "):", sep="")
    for v in violations:
        print(" -", v)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
