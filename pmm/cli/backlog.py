from __future__ import annotations

import argparse

from pmm.runtime.embeddings_backlog import process_backlog
from pmm.storage.eventlog import EventLog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pmm-backlog",
        description="Process embeddings backlog for response events (idempotent).",
    )
    parser.add_argument(
        "--db",
        default=".data/pmm.db",
        help="Path to PMM SQLite DB (default: .data/pmm.db)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="Optional max number of missing items to process this run.",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help=(
            "Use the real embedding provider for backlog processing. "
            "Default without --real performs a safe no-provider pass (skips)."
        ),
    )
    args = parser.parse_args(argv)

    log = EventLog(str(args.db))
    summary = process_backlog(log, batch_limit=args.batch, use_real=bool(args.real))
    print(
        f"Processed={summary['processed']} indexed={summary['indexed']} skipped={summary['skipped']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
