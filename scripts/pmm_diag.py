#!/usr/bin/env python3
# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# -----------------------------------------------------------
# PMM Diagnostic Script – now with Inter-Ledger References
# -----------------------------------------------------------
#   • All previous metrics (counts, cadence, commitments, …)
#   • **inter_ledger_ref** counts + verification stats
#   • **REF:** line extraction from assistant/reflection text
#   • JSON output unchanged (just extra keys)
#
# Usage:   python pmm_diag.py pmm.db
# -----------------------------------------------------------

import sqlite3
import json
import sys
import datetime
from pathlib import Path
from collections import Counter


# ------------------------------------------------------------------
# 0. Helpers
# ------------------------------------------------------------------
def iso_to_dt(ts: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(ts)


def extract_refs(text: str) -> list[str]:
    """Return list of REF: lines (stripped)."""
    return [ln[5:].strip() for ln in text.splitlines() if ln.startswith("REF: ")]


# ------------------------------------------------------------------
# 1. Open DB
# ------------------------------------------------------------------
if len(sys.argv) < 2:
    # Default to standard PMM location if not provided
    default_path = Path(".data/pmmdb/pmm.db")
    if not default_path.exists():
        print("Usage: python pmm_diag.py <pmm_database.db>")
        sys.exit(1)
    db_path = default_path
else:
    db_path = Path(sys.argv[1])
conn = sqlite3.connect(db_path)
c = conn.cursor()

diagnostics: dict = {}

# ------------------------------------------------------------------
# 2. Basic summary
# ------------------------------------------------------------------
c.execute("SELECT COUNT(*), MAX(id) FROM events")
total, max_id = c.fetchone()
diagnostics["summary"] = {"total_events": total, "last_event_id": max_id}
print("\n=== PMM Ledger Summary ===")
print(f"Events: {total:,}   Last ID: {max_id}")

# ------------------------------------------------------------------
# 3. Counts by kind (including new inter_ledger_ref)
# ------------------------------------------------------------------
print("\n-- Counts by kind --")
kinds = {}
c.execute("SELECT kind, COUNT(*) FROM events GROUP BY kind ORDER BY COUNT(*) DESC")
for kind, n in c.fetchall():
    print(f"{kind:25} {n}")
    kinds[kind] = n
diagnostics["counts_by_kind"] = kinds

# ------------------------------------------------------------------
# 4. Reflection cadence
# ------------------------------------------------------------------
print("\n-- Reflection cadence --")
c.execute("SELECT ts FROM events WHERE kind='reflection' ORDER BY id")
rows = [iso_to_dt(r[0]) for r in c.fetchall()]
intervals = []
if len(rows) > 1:
    for i in range(1, len(rows)):
        delta = (rows[i] - rows[i - 1]).total_seconds()
        intervals.append(delta)
avg = sum(intervals) / len(intervals) if intervals else None
diagnostics["reflection_intervals"] = {
    "count": len(intervals),
    "average_seconds": round(avg, 2) if avg else None,
}
for i in range(1, len(rows)):
    print(
        f"{rows[i-1].strftime('%H:%M:%S')} → {rows[i].strftime('%H:%M:%S')}  Δ={intervals[i-1]:.2f}s"
    )

# ------------------------------------------------------------------
# 5. Commitment statistics
# ------------------------------------------------------------------
print("\n-- Commitments --")
open_cnt = c.execute(
    "SELECT COUNT(*) FROM events WHERE kind='commitment_open'"
).fetchone()[0]
closed_cnt = c.execute(
    "SELECT COUNT(*) FROM events WHERE kind='commitment_close'"
).fetchone()[0]
diagnostics["commitments"] = {
    "open": open_cnt,
    "closed": closed_cnt,
    "ratio": round(open_cnt / closed_cnt, 2) if closed_cnt else None,
}
print(f"Open: {open_cnt}   Closed: {closed_cnt}")

# ------------------------------------------------------------------
# 6. Autonomy tick frequency
# ------------------------------------------------------------------
print("\n-- Autonomy tick frequency --")
c.execute("SELECT ts FROM events WHERE kind='autonomy_tick' ORDER BY id")
ticks = [iso_to_dt(r[0]) for r in c.fetchall()]
tick_ints = []
if len(ticks) > 1:
    for i in range(1, len(ticks)):
        delta = (ticks[i] - ticks[i - 1]).total_seconds()
        tick_ints.append(delta)
avg_tick = sum(tick_ints) / len(tick_ints) if tick_ints else None
diagnostics["autonomy_ticks"] = {
    "count": len(ticks),
    "average_interval_seconds": round(avg_tick, 2) if avg_tick else None,
}
print(
    f"Ticks: {len(ticks)}   Avg interval: {avg_tick:.2f}s" if avg_tick else "No ticks"
)

# ------------------------------------------------------------------
# 7. Hash-chain integrity
# ------------------------------------------------------------------
print("\n-- Hash-chain integrity --")
c.execute("SELECT id, prev_hash, hash FROM events ORDER BY id")
rows = c.fetchall()
breaks = []
for i in range(1, len(rows)):
    if rows[i - 1][2] != rows[i][1]:
        breaks.append(rows[i][0])
diagnostics["hash_integrity"] = {
    "breaks_found": len(breaks),
    "break_ids": breaks,
    "status": "ok" if not breaks else "broken",
}
print("Hash chain continuous" if not breaks else f"Breaks at IDs: {breaks}")

# ------------------------------------------------------------------
# 8. **NEW** Inter-ledger reference diagnostics
# ------------------------------------------------------------------
print("\n-- Inter-ledger references (Sprint 14) --")
c.execute(
    """SELECT content, meta FROM events WHERE kind='inter_ledger_ref' ORDER BY id"""
)
ref_rows = c.fetchall()

ref_stats = {
    "total": len(ref_rows),
    "verified": 0,
    "failed": 0,
    "paths": Counter(),
    "referenced_event_ids": Counter(),
    "raw_refs": [],
}
for content, meta_json in ref_rows:
    meta = json.loads(meta_json) if meta_json else {}
    verified = meta.get("verified", False)
    ref_stats["verified" if verified else "failed"] += 1
    # Parse "REF: path#id"
    if content.startswith("REF: "):
        raw = content[5:].strip()
        ref_stats["raw_refs"].append(raw)
        try:
            path, eid = raw.rsplit("#", 1)
            ref_stats["paths"][path] += 1
            ref_stats["referenced_event_ids"][int(eid)] += 1
        except Exception:
            pass

diagnostics["inter_ledger_refs"] = ref_stats

print(
    f"Total refs: {ref_stats['total']}   Verified: {ref_stats['verified']}   Failed: {ref_stats['failed']}"
)
if ref_stats["paths"]:
    print("  Most referenced ledgers:")
    for p, n in ref_stats["paths"].most_common(3):
        print(f"    {p}: {n}")

# ------------------------------------------------------------------
# 9. **NEW** Count of REF: lines inside assistant/reflection text
# ------------------------------------------------------------------
print("\n-- REF: lines inside assistant & reflection messages --")
c.execute(
    """SELECT kind, content FROM events
       WHERE kind IN ('assistant_message','reflection')
       ORDER BY id"""
)
msg_rows = c.fetchall()
ref_line_counter = Counter()
for kind, txt in msg_rows:
    refs = extract_refs(txt)
    if refs:
        ref_line_counter[kind] += len(refs)

diagnostics["ref_lines_in_messages"] = dict(ref_line_counter)
for k, n in ref_line_counter.items():
    print(f"{k:20} {n} REF: line(s)")

# ------------------------------------------------------------------
# 10. Write JSON report
# ------------------------------------------------------------------
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
out_file = db_path.with_name(f"pmm_diag_{ts}.json")
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(diagnostics, f, indent=2, default=str)

print(f"\nDiagnostics → {out_file.name}")
conn.close()
