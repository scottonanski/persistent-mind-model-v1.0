#!/usr/bin/env python3
# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski
#
# PMM — small_telemetry.py
# Lightweight export for AI model consumption (<5 MB typical)

import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def export_small():
    repo_root = Path(__file__).resolve().parent.parent
    db_path = repo_root / ".data" / "pmmdb" / "pmm.db"
    if not db_path.exists():
        print(f"[ERROR] Missing database: {db_path}")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    out_path = repo_root / f"chat_session_{now}_small_telemetry.md"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, ts, kind, meta, prev_hash, hash
        FROM events
        ORDER BY id DESC
        LIMIT 250
    """
    )
    rows = list(reversed(cur.fetchall()))
    conn.close()

    total = len(rows)
    digest = sha256("".join(r[5] or "" for r in rows))
    lines = [
        "# Persistent Mind Model — Small Telemetry Export",
        f"**Exported:** {now.replace('_',' ')} UTC",
        f"**Total Events:** {total}",
        f"**SHA256 Digest:** `{digest}`",
        "---",
        "| ID | Kind | Meta Preview | Prev Hash | Hash |",
        "|----|------|--------------|-----------|------|",
    ]

    for eid, ts, kind, meta, prev_hash, hsh in rows:
        preview = ""
        if meta and meta.strip() not in ("{}", "null", "NULL"):
            meta_str = meta.replace("\n", " ").strip()
            preview = meta_str[:300] + ("…" if len(meta_str) > 300 else "")
        lines.append(
            f"| {eid} | {kind} | {preview or '—'} | `{prev_hash or '∅'}` | `{hsh or '∅'}` |"
        )

    lines.append("\n---\n_End of small telemetry export._\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Small telemetry file → {out_path}")


if __name__ == "__main__":
    export_small()
