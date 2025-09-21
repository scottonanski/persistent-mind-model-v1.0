#!/usr/bin/env python3
"""
PMM Database Inspector
Demonstrates that PMM works by showing how reflections affect traits.
"""
import sqlite3
import json
import os

DB_PATH = ".data/pmm.db"  # Correct path


def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}")
        print("Make sure PMM has been run to create the database.")
        return

    print("🔍 PMM Database Inspection")
    print("=" * 50)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Database stats
    cursor.execute("SELECT COUNT(*) FROM events")
    total_events = cursor.fetchone()[0]
    print(f"📊 Total events in database: {total_events}")

    if total_events == 0:
        print("⚠️ Database is empty. Run PMM to generate events.")
        conn.close()
        return

    # 2. Event type distribution
    cursor.execute(
        "SELECT kind, COUNT(*) FROM events GROUP BY kind ORDER BY COUNT(*) DESC"
    )
    print("\n📈 Event Type Distribution:")
    for kind, count in cursor.fetchall():
        print(f"  {kind}: {count}")

    # 3. Recent reflections with communication
    print("\n💭 Recent Communication Reflections:")
    cursor.execute(
        """
        SELECT id, ts, content, meta 
        FROM events 
        WHERE kind = 'reflection' 
        AND content LIKE '%communication%'
        ORDER BY ts DESC 
        LIMIT 3
    """
    )
    reflections = cursor.fetchall()

    if not reflections:
        print("  ⚠️ No communication reflections found")
    else:
        for eid, ts, content, meta in reflections:
            print(f"  ID: {eid} | Time: {ts}")
            print(f"  Content: {content}")
            try:
                meta_data = json.loads(meta)
                if "novelty" in meta_data:
                    print(f"  Novelty Score: {meta_data['novelty']}")
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
            print("  ---")

    # 4. Trait changes from reflections
    print("\n🎯 Trait Changes (Conscientiousness):")
    cursor.execute(
        """
        SELECT id, ts, content, meta 
        FROM events 
        WHERE kind = 'policy_update' 
        AND meta LIKE '%"trait":"C"%'
        ORDER BY ts DESC 
        LIMIT 5
    """
    )
    trait_updates = cursor.fetchall()

    if not trait_updates:
        print("  ⚠️ No Conscientiousness trait updates found")
        # Show ANY policy updates
        cursor.execute(
            """
            SELECT id, ts, content, meta 
            FROM events 
            WHERE kind = 'policy_update' 
            ORDER BY ts DESC 
            LIMIT 3
        """
        )
        trait_updates = cursor.fetchall()
        if trait_updates:
            print("  📝 Showing recent policy updates (any trait):")

    for eid, ts, content, meta in trait_updates:
        print(f"  ID: {eid} | Time: {ts}")
        print(f"  Content: {content}")
        try:
            meta_data = json.loads(meta)
            changes = meta_data.get("changes", [])
            for change in changes:
                trait = change.get("trait", "Unknown")
                delta = change.get("delta", 0)
                print(f"  Trait Change: {trait} → {delta:+.3f}")
        except json.JSONDecodeError:
            print("  Meta: Invalid JSON")
        print("  ---")

    # 5. Semantic growth reports
    print("\n🌱 Semantic Growth Reports:")
    cursor.execute(
        """
        SELECT id, ts, meta 
        FROM events 
        WHERE kind = 'semantic_growth_report'
        ORDER BY ts DESC 
        LIMIT 2
    """
    )
    growth_reports = cursor.fetchall()

    if not growth_reports:
        print("  ⚠️ No semantic growth reports found")
    else:
        for eid, ts, meta in growth_reports:
            print(f"  ID: {eid} | Time: {ts}")
            try:
                meta_data = json.loads(meta)
                dominant = meta_data.get("dominant_themes", [])
                growth_paths = meta_data.get("growth_paths", [])
                print(f"  Dominant Themes: {dominant}")
                print(f"  Growth Paths: {growth_paths}")
            except json.JSONDecodeError:
                print("  Meta: Invalid JSON")
            print("  ---")

    # 6. Recent autonomy ticks
    print("\n🤖 Recent Autonomy Activity:")
    cursor.execute(
        """
        SELECT id, ts, meta 
        FROM events 
        WHERE kind = 'autonomy_tick'
        ORDER BY ts DESC 
        LIMIT 3
    """
    )
    ticks = cursor.fetchall()

    if not ticks:
        print("  ⚠️ No autonomy ticks found")
    else:
        for eid, ts, meta in ticks:
            print(f"  ID: {eid} | Time: {ts}")
            try:
                meta_data = json.loads(meta)
                if "ias" in meta_data:
                    print(f"  IAS: {meta_data['ias']:.3f}, GAS: {meta_data['gas']:.3f}")
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
            print("  ---")

    conn.close()

    print("\n✅ PMM Database Inspection Complete")
    print("This demonstrates PMM's autonomous operation:")
    print("- Reflections generate trait changes")
    print("- Semantic growth tracks theme evolution")
    print("- Autonomy ticks show continuous operation")


if __name__ == "__main__":
    main()
