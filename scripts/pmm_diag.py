# -----------------------------------------------------------
# PMM Diagnostic Script with JSON Output
# -----------------------------------------------------------
# This tool analyzes a Persistent Mind Model (PMM) ledger.
# It reads events from a SQLite database and outputs:
#   • Basic ledger metrics
#   • Event counts by kind
#   • Reflection cadence (intervals between reflections)
#   • Commitment statistics (open vs closed)
#   • Autonomy tick frequency
#   • Hash-chain integrity verification
#   • All results saved as JSON for auditing
#
# Usage:
#   python pmm_diag.py pmm_v2.db
# -----------------------------------------------------------

import sqlite3
import json
import sys
import datetime
from pathlib import Path

# --- Get database path from command-line argument ---
if len(sys.argv) < 2:
    print("Usage: python pmm_diag.py <pmm_database.db>")
    sys.exit(1)

db_path = Path(sys.argv[1])
conn = sqlite3.connect(db_path)
c = conn.cursor()

diagnostics = {}  # store everything for JSON output

# -----------------------------------------------------------
# 1. Basic summary: total events and last event ID
# -----------------------------------------------------------
print("\n=== PMM Diagnostic Summary ===")
c.execute("SELECT COUNT(*), MAX(id) FROM events")
total, maxid = c.fetchone()
print(f"Events: {total}, Last ID: {maxid}")
diagnostics["summary"] = {"total_events": total, "last_event_id": maxid}

# -----------------------------------------------------------
# 2. Counts by kind
# -----------------------------------------------------------
print("\n-- Counts by kind --")
kinds = {}

# Repeat the aggregate expression instead of using alias "n"
for kind, n in c.execute(
    "SELECT kind, COUNT(*) as count FROM events GROUP BY kind ORDER BY COUNT(*) DESC"
):
    print(f"{kind:20} {n}")
    kinds[kind] = n

diagnostics["counts_by_kind"] = kinds

# -----------------------------------------------------------
# 3. Reflection cadence (intervals between reflection events)
# -----------------------------------------------------------
print("\n-- Reflection cadence --")
c.execute("SELECT ts FROM events WHERE kind='reflection' ORDER BY id")
rows = [datetime.datetime.fromisoformat(ts[0]) for ts in c.fetchall()]
intervals = []
if len(rows) > 1:
    for i in range(1, len(rows)):
        delta = (rows[i] - rows[i - 1]).total_seconds()
        intervals.append(delta)
        print(f"{rows[i-1]} → {rows[i]}  Δ={delta:.2f}s")
avg_interval = sum(intervals) / len(intervals) if intervals else None
diagnostics["reflection_intervals"] = {
    "count": len(intervals),
    "average_seconds": avg_interval,
}

# -----------------------------------------------------------
# 4. Commitment statistics
# -----------------------------------------------------------
print("\n-- Commitments (open vs closed) --")
open_count = c.execute(
    "SELECT COUNT(*) FROM events WHERE kind='commitment_open'"
).fetchone()[0]
closed_count = c.execute(
    "SELECT COUNT(*) FROM events WHERE kind='commitment_close'"
).fetchone()[0]
print(f"Open: {open_count}, Closed: {closed_count}")
diagnostics["commitments"] = {
    "open": open_count,
    "closed": closed_count,
    "open_to_closed_ratio": (
        round(open_count / closed_count, 2) if closed_count else None
    ),
}

# -----------------------------------------------------------
# 5. Autonomy tick frequency
# -----------------------------------------------------------
print("\n-- Autonomy tick frequency --")
c.execute("SELECT ts FROM events WHERE kind='autonomy_tick' ORDER BY id")
ticks = [datetime.datetime.fromisoformat(ts[0]) for ts in c.fetchall()]
tick_intervals = []
if len(ticks) > 1:
    for i in range(1, len(ticks)):
        delta = (ticks[i] - ticks[i - 1]).total_seconds()
        tick_intervals.append(delta)
avg_tick_interval = (
    sum(tick_intervals) / len(tick_intervals) if tick_intervals else None
)
print(
    f"Ticks: {len(ticks)}, Avg interval: {avg_tick_interval:.2f}s"
    if avg_tick_interval
    else "No tick data."
)
diagnostics["autonomy_ticks"] = {
    "count": len(ticks),
    "average_interval_seconds": avg_tick_interval,
}

# -----------------------------------------------------------
# 6. Hash-chain integrity check
# -----------------------------------------------------------
print("\n-- Hash integrity check --")
rows = c.execute("SELECT id, prev_hash, hash FROM events ORDER BY id").fetchall()
hash_breaks = []
for i in range(1, len(rows)):
    prev = rows[i - 1][2]
    if prev != rows[i][1]:
        hash_breaks.append(rows[i][0])
if hash_breaks:
    print(f"⚠️  Hash break(s) detected at event IDs: {hash_breaks}")
else:
    print("✅ Hash chain continuous (no breaks detected)")
diagnostics["hash_integrity"] = {
    "breaks_found": len(hash_breaks),
    "break_ids": hash_breaks,
    "status": "ok" if not hash_breaks else "broken",
}

# -----------------------------------------------------------
# 7. Output results to JSON file
# -----------------------------------------------------------
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = db_path.with_name(f"pmm_diag_{timestamp}.json")

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(diagnostics, f, indent=2, default=str)

print(f"\n📄 Diagnostics written to {output_file.name}")
conn.close()
