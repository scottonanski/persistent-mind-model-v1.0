import sqlite3
import json
from pathlib import Path

DB_PATH = Path(".data/pmm.db")
OUT_PATH = Path("analyze_reflections_results.txt")


def load_events(kinds):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in kinds)
    cursor.execute(
        f"SELECT id, ts, kind, content, meta FROM events "
        f"WHERE kind IN ({placeholders}) ORDER BY id DESC",
        kinds,
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def dump_reflections(f):
    f.write("=== Last 10 Reflections ===\n\n")
    reflections = load_events(["reflection"])[:10]
    for rid, ts, kind, content, meta in reflections:
        meta_json = json.loads(meta) if meta else {}
        snippet = (content or "").strip().replace("\n", " ")[:100]
        f.write(f"Reflection ID: {rid}, Time: {ts}\n")
        f.write(f"  Content: {snippet}\n")
        if meta_json:
            f.write(f"  Meta: {json.dumps(meta_json)}\n")
        f.write("\n")


def dump_trait_drift(f):
    f.write("=== Trait Drift Events ===\n\n")
    traits = load_events(["trait_update"])
    if not traits:
        f.write("⚠️ No trait updates found.\n\n")
        return
    for rid, ts, kind, content, meta in traits:
        meta_json = json.loads(meta) if meta else {}
        f.write(f"{ts}: {meta_json}\n")
    f.write("\n")


def dump_semantic_growth(f):
    f.write("=== Semantic Growth Reports ===\n\n")
    reports = load_events(["semantic_growth_report"])
    if not reports:
        f.write("⚠️ No semantic growth reports found.\n\n")
        return

    for rid, ts, kind, content, meta in reports:
        meta_json = json.loads(meta) if meta else {}
        themes = meta_json.get("analysis", {}).get("dominant_themes", [])
        growth_paths = meta_json.get("growth_paths", [])

        f.write(f"Growth Report ID: {rid}, Time: {ts}\n")
        f.write(f"  Themes: {themes}\n")
        f.write(f"  Growth Paths: {growth_paths}\n")
        f.write(f"  Analysis: {json.dumps(meta_json.get('analysis', {}))}\n")
        f.write("\n")


def dump_commitments(f):
    f.write("=== Commitment Timeline (latest 20) ===\n\n")
    commits = load_events(["commitment_open", "commitment_close"])[:20]
    for rid, ts, kind, content, meta in commits:
        meta_json = json.loads(meta) if meta else {}
        f.write(f"{ts}: {kind} {content} {meta_json}\n")
    f.write("\n")


def dump_metrics(f):
    f.write("=== Metrics Updates (latest 10) ===\n\n")
    metrics = load_events(["metrics_update"])[:10]
    if not metrics:
        f.write("⚠️ No metrics updates found.\n\n")
        return

    for rid, ts, kind, content, meta in metrics:
        meta_json = json.loads(meta) if meta else {}
        ias = meta_json.get("IAS", "N/A")
        gas = meta_json.get("GAS", "N/A")
        reason = meta_json.get("reason", "N/A")
        f.write(f"Metrics ID: {rid}, Time: {ts}\n")
        f.write(f"  IAS: {ias}, GAS: {gas}, Reason: {reason}\n")
        f.write(f"  Meta: {json.dumps(meta_json)}\n")
        f.write("\n")


def main():
    """Analyze PMM reflections and related events."""
    if not DB_PATH.exists():
        print(f"❌ Database not found at: {DB_PATH}")
        print("Make sure PMM has been run to create the database.")
        return

    print("🔍 PMM Reflection Analysis")
    print("=" * 50)

    with open(OUT_PATH, "w") as f:
        dump_reflections(f)
        dump_trait_drift(f)
        dump_semantic_growth(f)
        dump_commitments(f)
        dump_metrics(f)

    print(f"✅ Analysis written to: {OUT_PATH}")
    print("Open analyze_reflections_results.txt to view the results.")


if __name__ == "__main__":
    main()
