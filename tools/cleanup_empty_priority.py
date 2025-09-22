"""Cleanup utility for removing empty commitment priority telemetry.

Run in dry-run mode by default to report the number of deletable events.
Invoke with ``--apply`` to mutate the provided database (typically a backup).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    db_path = (
        Path(argv[1])
        if len(argv) > 1 and argv[1] != "--apply"
        else Path(".data/pmm.pre_fix.db")
    )
    apply = "--apply" in argv

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        rows = cur.execute(
            'SELECT id, meta FROM events WHERE kind="commitment_priority"'
        ).fetchall()
        to_delete: list[int] = []
        for row_id, meta_json in rows:
            try:
                meta = json.loads(meta_json)
            except json.JSONDecodeError:
                continue
            if meta.get("ranking") == []:
                to_delete.append(row_id)
        print(f"Empty commitment_priority events: {len(to_delete)}")
        if apply and to_delete:
            placeholders = ",".join("?" for _ in to_delete)
            cur.execute(
                f"DELETE FROM events WHERE id IN ({placeholders})",
                to_delete,
            )
            conn.commit()
            print(f"Deleted: {len(to_delete)}")
    finally:
        conn.close()
    if apply and not to_delete:
        print("No events deleted (none matched criteria).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
