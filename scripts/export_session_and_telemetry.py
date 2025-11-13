#!/usr/bin/env python3
# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski
#
# PMM — Triple Exporter (Readable / Telemetry / Ledger)
# Generates linked exports:
#  1. Human-readable chat transcript
#  2. Telemetry summary for auditing
#  3. Compressed raw ledger JSON for AI verification

import sqlite3
import json
import gzip
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
import textwrap


def sha256(data: str) -> str:
    """Return SHA256 digest of provided string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def export_session():
    repo_root = Path(__file__).resolve().parent.parent
    db_path = repo_root / ".data" / "pmmdb" / "pmm.db"
    if not db_path.exists():
        print(f"[ERROR] PMM database not found at {db_path}")
        return

    # Common timestamp key
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    readable_path = repo_root / f"chat_session_{now}_readable.md"
    telemetry_path = repo_root / f"chat_session_{now}_telemetry.md"
    ledger_path = repo_root / f"chat_session_{now}_ledger.json.gz"

    # Query all events
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, ts, kind, content, meta, prev_hash, hash
        FROM events
        ORDER BY id ASC
    """
    )
    rows = cursor.fetchall()
    conn.close()

    # Build counters and state trackers
    kinds = Counter()
    breaks = []
    continuity = []
    chat_msgs = []

    # --- Ledger export data (for gzip) ---
    raw_ledger = []

    for eid, ts, kind, content, meta, prev_hash, hsh in rows:
        kinds[kind] += 1
        raw_ledger.append(
            {
                "id": eid,
                "ts": ts,
                "kind": kind,
                "content": content,
                "meta": meta,
                "prev_hash": prev_hash,
                "hash": hsh,
            }
        )

        # Detect continuity gaps
        if continuity and prev_hash and prev_hash != continuity[-1]:
            breaks.append((eid, continuity[-1], prev_hash))
        continuity.append(hsh)

        # Collect visible chat messages
        if kind in {"user_message", "assistant_message"}:
            visible = textwrap.dedent(content).strip()
            if kind == "assistant_message":
                hidden_prefixes = ("COMMIT:", "CLOSE:", "CLAIM:", "REFLECT:")
                visible = "\n".join(
                    line
                    for line in visible.splitlines()
                    if not line.startswith(hidden_prefixes)
                ).strip()
            chat_msgs.append((kind, ts, visible))

    # ============================================================
    # 1. Human-readable Markdown (chat only)
    # ============================================================
    readable = []
    readable.append("# Persistent Mind Model — Readable Chat Log\n")
    readable.append(f"**Exported:** {now.replace('_',' ')} UTC\n")
    readable.append(f"**Linked Telemetry:** `{telemetry_path.name}`  \n")
    readable.append(f"**Linked Ledger:** `{ledger_path.name}`\n")
    readable.append("---\n")

    for idx, (kind, ts, content) in enumerate(chat_msgs, start=1):
        role = "👤 User" if kind == "user_message" else "🤖 Echo"
        readable.append(f"### Turn {idx}: {role}\n*{ts}*\n\n```text\n{content}\n```\n")

    readable.append(
        "\n---\n_End of readable log — see telemetry or ledger for verification._\n"
    )

    with open(readable_path, "w", encoding="utf-8") as f:
        f.write("\n".join(readable))

    # ============================================================
    # 2. Telemetry Markdown (condensed)
    # ============================================================
    telemetry = []
    telemetry.append("# Persistent Mind Model — Telemetry Summary\n")
    telemetry.append(f"**Exported:** {now.replace('_',' ')} UTC\n")
    telemetry.append(f"**Linked Readable:** `{readable_path.name}`  \n")
    telemetry.append(f"**Linked Ledger:** `{ledger_path.name}`\n")
    telemetry.append("---\n")

    telemetry.append("## 📜 Event Summary\n\n")
    telemetry.append("| ID | Kind | Meta Keys | Prev Hash | Hash |\n")
    telemetry.append("|----|------|------------|-----------|------|\n")

    for eid, ts, kind, content, meta, prev_hash, hsh in rows:
        # truncate meta for readability
        meta_display = (
            meta.strip().replace("\n", " ")
            if meta and meta.strip() not in ("{}", "null", "NULL")
            else ""
        )
        if len(meta_display) > 500:
            meta_display = meta_display[:500] + "…"
        try:
            meta_keys = list(json.loads(meta).keys()) if meta_display else []
        except Exception:
            meta_keys = []
        telemetry.append(
            f"| {eid} | {kind} | {', '.join(meta_keys) or '—'} | `{prev_hash or '∅'}` | `{hsh or '∅'}` |\n"
        )

    telemetry.append("\n## 📊 Statistics\n\n")
    telemetry.append(f"- **Total Events:** {len(rows)}\n")
    telemetry.append(f"- **Event Types:** {len(kinds)}\n")
    telemetry.append("\n| Kind | Count |\n|------|-------:|\n")
    for k, c in kinds.items():
        telemetry.append(f"| {k} | {c} |\n")
    telemetry.append("\n")

    if breaks:
        telemetry.append("⚠️ **Continuity Breaks Detected:**\n")
        for eid, prev, actual in breaks:
            telemetry.append(f"- Event {eid}: expected `{prev}` but saw `{actual}`\n")
    else:
        telemetry.append("✅ **No hash continuity breaks detected.**\n")

    # Manifest for AI verification
    manifest = {
        "export_timestamp": now,
        "linked_readable": readable_path.name,
        "linked_ledger": ledger_path.name,
        "total_events": len(rows),
        "event_type_counts": dict(kinds),
        "continuity_breaks": len(breaks),
        # Digest over event hashes (column 6), not prev_hash
        "sha256_full_digest": sha256("".join(r[6] or "" for r in rows)),
    }
    telemetry.append("\n## 🧾 Verification Manifest\n\n```json\n")
    telemetry.append(json.dumps(manifest, indent=2, ensure_ascii=False))
    telemetry.append("\n```\n\n---\n_End of telemetry summary._\n")

    with open(telemetry_path, "w", encoding="utf-8") as f:
        f.write("\n".join(telemetry))

    # ============================================================
    # 3. Compressed JSON Ledger
    # ============================================================
    with gzip.open(ledger_path, "wt", encoding="utf-8") as f:
        json.dump(raw_ledger, f, indent=2, ensure_ascii=False)

    print(
        f"[OK] Export complete →\n  {readable_path}\n  {telemetry_path}\n  {ledger_path}"
    )


if __name__ == "__main__":
    export_session()
