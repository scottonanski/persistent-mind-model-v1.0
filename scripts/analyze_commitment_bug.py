#!/usr/bin/env python3
"""Analyze commitment bug in existing database."""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pmm.storage.eventlog import EventLog


def analyze_commitments(db_path: str):
    """Analyze commitment events in database."""

    print("=" * 70)
    print(f"COMMITMENT BUG ANALYSIS: {Path(db_path).name}")
    print("=" * 70)
    print()

    log = EventLog(db_path)
    events = log.read_all()

    # Categorize events
    commitment_opens = []
    commitment_closes = []
    commitment_expires = []
    commitment_scans = []
    commitment_debugs = []
    commitment_errors = []

    for evt in events:
        kind = evt.get("kind")
        if kind == "commitment_open":
            commitment_opens.append(evt)
        elif kind == "commitment_close":
            commitment_closes.append(evt)
        elif kind == "commitment_expire":
            commitment_expires.append(evt)
        elif kind == "commitment_scan":
            commitment_scans.append(evt)
        elif kind == "commitment_debug":
            commitment_debugs.append(evt)
        elif kind == "commitment_error":
            commitment_errors.append(evt)

    print(f"Total events: {len(events)}")
    print(f"  commitment_open:   {len(commitment_opens)}")
    print(f"  commitment_close:  {len(commitment_closes)}")
    print(f"  commitment_expire: {len(commitment_expires)}")
    print(f"  commitment_scan:   {len(commitment_scans)}")
    print(f"  commitment_debug:  {len(commitment_debugs)}")
    print(f"  commitment_error:  {len(commitment_errors)}")
    print()

    # Analyze opens
    if commitment_opens:
        print("COMMITMENT OPENS")
        print("-" * 70)
        cid_to_text = {}
        for evt in commitment_opens[:10]:  # Show first 10
            meta = evt.get("meta", {})
            cid = meta.get("cid")
            text = meta.get("text", "")
            cid_to_text[cid] = text
            print(f"  Event {evt.get('id'):4d} | CID: {cid}")
            print(f"             | Text: {text[:60]}...")

        if len(commitment_opens) > 10:
            print(f"  ... and {len(commitment_opens) - 10} more")
        print()
    else:
        print("⚠️  NO COMMITMENT_OPEN EVENTS FOUND")
        print()

    # Analyze closes
    if commitment_closes:
        print("COMMITMENT CLOSES")
        print("-" * 70)
        for evt in commitment_closes[:10]:
            meta = evt.get("meta", {})
            cid = meta.get("cid")
            evidence = meta.get("evidence", "")
            print(f"  Event {evt.get('id'):4d} | CID: {cid}")
            print(f"             | Evidence: {evidence[:60]}...")

        if len(commitment_closes) > 10:
            print(f"  ... and {len(commitment_closes) - 10} more")
        print()
    else:
        print("⚠️  NO COMMITMENT_CLOSE EVENTS FOUND")
        print()

    # Analyze scans (extraction attempts)
    if commitment_scans:
        print("COMMITMENT SCANS (Extraction Attempts)")
        print("-" * 70)

        accepted_count = 0
        rejected_count = 0
        scores = []

        for evt in commitment_scans:
            meta = evt.get("meta", {})
            count = meta.get("accepted_count", 0)
            score = meta.get("best_score", 0.0)

            if count > 0:
                accepted_count += count
            else:
                rejected_count += 1

            scores.append(score)

        print(f"  Total scans: {len(commitment_scans)}")
        print(f"  Accepted: {accepted_count}")
        print(f"  Rejected: {rejected_count}")

        if scores:
            avg_score = sum(scores) / len(scores)
            max_score = max(scores)
            print(f"  Avg score: {avg_score:.3f}")
            print(f"  Max score: {max_score:.3f}")

        # Show some rejected scans with high scores
        high_score_rejects = [
            evt
            for evt in commitment_scans
            if evt.get("meta", {}).get("accepted_count", 0) == 0
            and evt.get("meta", {}).get("best_score", 0.0) > 0.6
        ]

        if high_score_rejects:
            print("\n  High-score rejections (score > 0.6):")
            for evt in high_score_rejects[:5]:
                meta = evt.get("meta", {})
                score = meta.get("best_score", 0.0)
                intent = meta.get("best_intent", "")
                text = evt.get("content", "")[:60]
                print(f"    Score {score:.3f} | Intent: {intent}")
                print(f"             | Text: {text}...")
        print()

    # Analyze debug events (new diagnostic logging)
    if commitment_debugs:
        print("COMMITMENT DEBUG EVENTS (Successful Opens)")
        print("-" * 70)
        for evt in commitment_debugs[:10]:
            meta = evt.get("meta", {})
            cid = meta.get("cid")
            score = meta.get("score", 0.0)
            text = evt.get("content", "")
            print(f"  Event {evt.get('id'):4d} | CID: {cid} | Score: {score:.3f}")
            print(f"             | {text}")

        if len(commitment_debugs) > 10:
            print(f"  ... and {len(commitment_debugs) - 10} more")
        print()

    # Analyze error events
    if commitment_errors:
        print("COMMITMENT ERROR EVENTS")
        print("-" * 70)
        error_types = defaultdict(int)

        for evt in commitment_errors:
            meta = evt.get("meta", {})
            error_type = meta.get("error_type", "Unknown")
            error_types[error_type] += 1

        print(f"  Total errors: {len(commitment_errors)}")
        for error_type, count in error_types.items():
            print(f"    {error_type}: {count}")

        print("\n  Sample errors:")
        for evt in commitment_errors[:5]:
            meta = evt.get("meta", {})
            error = meta.get("error", "")
            text = evt.get("content", "")[:60]
            print(f"    Error: {error}")
            print(f"    Text:  {text}...")
        print()

    # Lifecycle analysis
    print("LIFECYCLE ANALYSIS")
    print("-" * 70)

    # Track CID lifecycle
    cid_lifecycle = defaultdict(lambda: {"opens": [], "closes": [], "expires": []})

    for evt in commitment_opens:
        cid = evt.get("meta", {}).get("cid")
        if cid:
            cid_lifecycle[cid]["opens"].append(evt.get("id"))

    for evt in commitment_closes:
        cid = evt.get("meta", {}).get("cid")
        if cid:
            cid_lifecycle[cid]["closes"].append(evt.get("id"))

    for evt in commitment_expires:
        cid = evt.get("meta", {}).get("cid")
        if cid:
            cid_lifecycle[cid]["expires"].append(evt.get("id"))

    # Categorize commitments
    never_closed = []
    closed_properly = []
    expired = []

    for cid, lifecycle in cid_lifecycle.items():
        if lifecycle["closes"]:
            closed_properly.append(cid)
        elif lifecycle["expires"]:
            expired.append(cid)
        else:
            never_closed.append(cid)

    print(f"  Total unique CIDs: {len(cid_lifecycle)}")
    print(f"  Closed properly: {len(closed_properly)}")
    print(f"  Expired: {len(expired)}")
    print(f"  Never closed/expired: {len(never_closed)}")

    if never_closed:
        print("\n  Sample never-closed commitments:")
        for cid in never_closed[:5]:
            lifecycle = cid_lifecycle[cid]
            print(f"    CID: {cid}")
            print(f"      Opened at events: {lifecycle['opens']}")

    print()

    # Summary
    print("=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)

    if not commitment_opens:
        print("❌ CRITICAL: No commitment_open events found")
        print("   → Extraction is completely broken")
    elif len(commitment_opens) < len(commitment_scans) * 0.1:
        print("⚠️  WARNING: Very low extraction rate")
        print(
            f"   → {len(commitment_scans)} scans but only {len(commitment_opens)} opens"
        )
        print("   → Threshold may be too high or extraction logic broken")
    else:
        print(f"✓ Extraction working: {len(commitment_opens)} commitments opened")

    if commitment_opens and not commitment_closes and not expired:
        print("❌ CRITICAL: Commitments opened but never closed or expired")
        print("   → Persistence bug: commitments vanish without lifecycle events")
    elif commitment_opens and len(never_closed) > len(closed_properly):
        print("⚠️  WARNING: Most commitments never closed")
        print("   → May indicate TTL expiration or projection bug")

    if commitment_errors:
        print(f"⚠️  WARNING: {len(commitment_errors)} commitment errors logged")
        print("   → Check error details above")

    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_commitment_bug.py <path_to_db>")
        print("\nExample:")
        print("  python scripts/analyze_commitment_bug.py .data/echo.db")
        sys.exit(1)

    db_path = sys.argv[1]

    if not Path(db_path).exists():
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    analyze_commitments(db_path)
