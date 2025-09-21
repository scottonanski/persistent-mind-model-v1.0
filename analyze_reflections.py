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

    empty_count = 0
    policy_count = 0
    quality_scores = []

    for rid, ts, kind, content, meta in reflections:
        meta_json = json.loads(meta) if meta else {}
        snippet = (content or "").strip().replace("\n", " ")[:100]

        # Check for empty reflections
        if not snippet or snippet.startswith("(empty"):
            empty_count += 1

        # Check for policy loops
        if (
            snippet.lower().count("policy") > 2
            or "novelty_threshold" in snippet.lower()
        ):
            policy_count += 1

        # Extract quality score if available
        quality_score = meta_json.get("quality_score")
        if quality_score is not None:
            quality_scores.append(quality_score)

        f.write(f"Reflection ID: {rid}, Time: {ts}\n")
        f.write(f"  Content: {snippet}\n")
        if meta_json:
            f.write(f"  Meta: {json.dumps(meta_json)}\n")
        f.write("\n")

    # Quality summary
    f.write("📊 **Reflection Quality Summary:**\n")
    f.write(f"  Empty reflections: {empty_count}/10 ({empty_count*10}%)\n")
    f.write(f"  Policy-heavy reflections: {policy_count}/10 ({policy_count*10}%)\n")
    if quality_scores:
        avg_quality = sum(quality_scores) / len(quality_scores)
        f.write(
            f"  Average quality score: {avg_quality:.3f} (from {len(quality_scores)} scored reflections)\n"
        )
    else:
        f.write("  No quality scores found in metadata\n")
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


def dump_reflection_quality_checks(f):
    f.write("=== Reflection Quality & Rejection Analysis ===\n\n")

    # Check for debug events with reflection rejections
    debug_events = load_events(["debug"])[:20]
    rejection_reasons = {}

    for rid, ts, kind, content, meta in debug_events:
        meta_json = json.loads(meta) if meta else {}
        reject_reason = meta_json.get("reflection_reject")
        if reject_reason:
            rejection_reasons[reject_reason] = (
                rejection_reasons.get(reject_reason, 0) + 1
            )
            f.write(f"Debug ID: {rid}, Time: {ts}\n")
            f.write(f"  Rejection Reason: {reject_reason}\n")
            f.write(f"  Scores: {meta_json.get('scores', {})}\n")
            f.write("\n")

    if rejection_reasons:
        f.write("📊 **Rejection Summary:**\n")
        for reason, count in rejection_reasons.items():
            f.write(f"  {reason}: {count} times\n")
    else:
        f.write("✅ No reflection rejections found in recent debug events\n")
    f.write("\n")

    # Check for reflection_check events
    f.write("=== Reflection Check Events (latest 10) ===\n\n")
    checks = load_events(["reflection_check"])[:10]
    if not checks:
        f.write("⚠️ No reflection_check events found.\n\n")
        return

    passed_count = 0
    failed_count = 0

    for rid, ts, kind, content, meta in checks:
        meta_json = json.loads(meta) if meta else {}
        ok = meta_json.get("ok", False)
        reason = meta_json.get("reason", "unknown")

        if ok:
            passed_count += 1
        else:
            failed_count += 1

        f.write(f"Check ID: {rid}, Time: {ts}\n")
        f.write(f"  Passed: {ok}, Reason: {reason}\n")
        f.write(f"  Meta: {json.dumps(meta_json)}\n")
        f.write("\n")

    f.write(f"📊 **Check Summary:** {passed_count} passed, {failed_count} failed\n\n")


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


def dump_stage_advancement(f):
    f.write("=== Stage Advancement Analysis ===\n\n")

    # Check for stage_update events
    stage_updates = load_events(["stage_update"])[:10]
    if not stage_updates:
        f.write("⚠️ No stage updates found.\n\n")
        return

    f.write("Recent Stage Transitions:\n")
    for rid, ts, kind, content, meta in stage_updates:
        meta_json = json.loads(meta) if meta else {}
        from_stage = meta_json.get("from_stage", "unknown")
        to_stage = meta_json.get("to_stage", "unknown")
        f.write(f"Stage Update ID: {rid}, Time: {ts}\n")
        f.write(f"  Transition: {from_stage} → {to_stage}\n")
        f.write(f"  Meta: {json.dumps(meta_json)}\n")
        f.write("\n")

    # Check current stage by looking at latest metrics
    metrics = load_events(["metrics_update"])[:1]
    if metrics:
        _, _, _, _, meta = metrics[0]
        meta_json = json.loads(meta) if meta else {}
        ias = meta_json.get("IAS", 0)
        gas = meta_json.get("GAS", 0)
        f.write(f"📊 **Current Metrics:** IAS={ias}, GAS={gas}\n")

        # Estimate current stage based on thresholds
        if ias >= 0.85 and gas >= 0.75:
            estimated_stage = "S4"
        elif ias >= 0.80 and gas >= 0.50:
            estimated_stage = "S3"
        elif ias >= 0.70 and gas >= 0.35:
            estimated_stage = "S2"
        elif ias >= 0.50 and gas >= 0.15:
            estimated_stage = "S1"
        else:
            estimated_stage = "S0"
        f.write(
            f"📊 **Estimated Stage:** {estimated_stage} (based on IAS/GAS thresholds)\n"
        )
    f.write("\n")


def main():
    """Analyze PMM reflections and related events."""
    if not DB_PATH.exists():
        print(f"❌ Database not found at: {DB_PATH}")
        print("Make sure PMM has been run to create the database.")
        return

    print("🔍 PMM Reflection Quality Analysis")
    print("=" * 50)

    with open(OUT_PATH, "w") as f:
        f.write("🔍 **PMM Reflection System Analysis**\n")
        f.write("=" * 50 + "\n\n")
        f.write("This analysis checks for the reflection system fixes:\n")
        f.write("- Empty reflection detection\n")
        f.write("- Policy loop prevention\n")
        f.write("- Quality-based stage advancement\n")
        f.write("- Reflection acceptance/rejection tracking\n\n")

        dump_reflections(f)
        dump_reflection_quality_checks(f)
        dump_stage_advancement(f)
        dump_semantic_growth(f)
        dump_trait_drift(f)
        dump_commitments(f)
        dump_metrics(f)

    print(f"✅ Analysis written to: {OUT_PATH}")
    print("Open analyze_reflections_results.txt to view the results.")
    print("\n🔍 Key things to check:")
    print("- Empty reflections should be 0% (or very low)")
    print("- Policy-heavy reflections should be reduced")
    print("- Rejection reasons should show quality gates working")
    print("- Stage advancement should require quality improvements")


if __name__ == "__main__":
    main()
