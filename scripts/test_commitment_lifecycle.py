#!/usr/bin/env python3
"""Test commitment lifecycle to diagnose persistence bug."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pmm.commitments.tracker import CommitmentTracker
from pmm.storage.eventlog import EventLog


def test_commitment_lifecycle():
    """Test full commitment lifecycle: open -> verify -> close -> verify."""

    print("=" * 60)
    print("COMMITMENT LIFECYCLE TEST")
    print("=" * 60)

    # Create test database
    test_db = Path(__file__).parent.parent / ".data" / "test_commitments.db"
    if test_db.exists():
        test_db.unlink()
        print("✓ Cleaned up old test database")

    # Initialize
    log = EventLog(str(test_db))
    tracker = CommitmentTracker(log)

    print(f"✓ Initialized tracker with database: {test_db}")
    print()

    # Test 1: Open a commitment
    print("TEST 1: Opening commitment")
    print("-" * 60)

    test_text = "I will test the commitment system thoroughly"
    cid = tracker.add_commitment(test_text, source="test_script")

    print(f"  Commitment text: {test_text}")
    print(f"  Returned CID: {cid}")

    if not cid:
        print("  ❌ FAILED: add_commitment returned None/empty")
        return False

    print("  ✓ Commitment opened successfully")
    print()

    # Test 2: Verify it appears in open commitments
    print("TEST 2: Verifying commitment appears in open map")
    print("-" * 60)

    opens = tracker._open_commitments_legacy()
    print(f"  Open commitments count: {len(opens)}")
    print(f"  Open commitment CIDs: {list(opens.keys())}")

    if cid not in opens:
        print(f"  ❌ FAILED: CID {cid} not found in open commitments")
        print(f"  Available CIDs: {list(opens.keys())}")
        return False

    commitment_data = opens[cid]
    print("  ✓ Found commitment in open map")
    print(f"  Commitment data: {commitment_data}")
    print()

    # Test 3: Check event log
    print("TEST 3: Checking event log")
    print("-" * 60)

    events = log.read_all()
    commitment_events = [e for e in events if e.get("kind") == "commitment_open"]

    print(f"  Total events: {len(events)}")
    print(f"  Commitment open events: {len(commitment_events)}")

    if not commitment_events:
        print("  ❌ FAILED: No commitment_open events in ledger")
        return False

    for evt in commitment_events:
        meta = evt.get("meta", {})
        print(f"  Event ID: {evt.get('id')}")
        print(f"    CID: {meta.get('cid')}")
        print(f"    Text: {meta.get('text', '')[:50]}...")

    print("  ✓ Commitment events found in ledger")
    print()

    # Test 4: Close the commitment
    print("TEST 4: Closing commitment")
    print("-" * 60)

    description = "Test completed successfully"
    close_result = tracker.close_with_evidence(
        cid,
        evidence_type="done",  # Must be "done" to actually close
        description=description,
    )

    print(f"  Description: {description}")
    print(f"  Close result: {close_result}")
    print()

    # Test 5: Verify it's no longer open
    print("TEST 5: Verifying commitment is closed")
    print("-" * 60)

    opens_after = tracker._open_commitments_legacy()
    print(f"  Open commitments count: {len(opens_after)}")
    print(f"  Open commitment CIDs: {list(opens_after.keys())}")

    if cid in opens_after:
        print(f"  ❌ FAILED: CID {cid} still in open commitments after close")
        return False

    print("  ✓ Commitment successfully closed")
    print()

    # Test 6: Check close event in log
    print("TEST 6: Checking close event in log")
    print("-" * 60)

    events_final = log.read_all()
    close_events = [e for e in events_final if e.get("kind") == "commitment_close"]

    print(f"  Total events: {len(events_final)}")
    print(f"  Commitment close events: {len(close_events)}")

    if not close_events:
        print("  ❌ FAILED: No commitment_close events in ledger")
        return False

    for evt in close_events:
        meta = evt.get("meta", {})
        print(f"  Event ID: {evt.get('id')}")
        print(f"    CID: {meta.get('cid')}")
        print(f"    Evidence: {meta.get('evidence', '')[:50]}...")

    print("  ✓ Close event found in ledger")
    print()

    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
    return True


def test_extraction_integration():
    """Test commitment extraction from text (as used in runtime)."""

    print("\n")
    print("=" * 60)
    print("EXTRACTION INTEGRATION TEST")
    print("=" * 60)

    test_db = Path(__file__).parent.parent / ".data" / "test_extraction.db"
    if test_db.exists():
        test_db.unlink()

    log = EventLog(str(test_db))
    tracker = CommitmentTracker(log)

    print("✓ Initialized tracker")
    print()

    # Test extraction via process_assistant_reply
    print("TEST: Extracting commitments from assistant reply")
    print("-" * 60)

    test_reply = """
    I will help you debug this issue. Let me analyze the commitment system
    and identify where the persistence is failing. I commit to providing
    a detailed diagnostic report by the end of this session.
    """

    print(f"  Test reply: {test_reply[:100]}...")
    print()

    opened_cids = tracker.process_assistant_reply(test_reply, reply_event_id=1)

    print(f"  Extracted commitments: {len(opened_cids)}")
    print(f"  CIDs: {opened_cids}")
    print()

    if not opened_cids:
        print("  ⚠️  No commitments extracted (may be below threshold)")

        # Check for debug events
        events = log.read_all()
        debug_events = [e for e in events if e.get("kind") == "commitment_debug"]
        error_events = [e for e in events if e.get("kind") == "commitment_error"]

        print(f"  Debug events: {len(debug_events)}")
        print(f"  Error events: {len(error_events)}")

        for evt in error_events:
            print(f"    Error: {evt.get('meta', {}).get('error')}")
    else:
        print(f"  ✓ Successfully extracted {len(opened_cids)} commitment(s)")

        # Verify they're in open map
        opens = tracker._open_commitments_legacy()
        print(f"  Open commitments in map: {len(opens)}")

        for cid in opened_cids:
            if cid in opens:
                print(f"    ✓ {cid} found in open map")
            else:
                print(f"    ❌ {cid} NOT in open map (persistence bug!)")

    print()
    print("=" * 60)


if __name__ == "__main__":
    try:
        # Run basic lifecycle test
        success = test_commitment_lifecycle()

        # Run extraction integration test
        test_extraction_integration()

        if success:
            print("\n✅ Basic commitment lifecycle works correctly")
            print("   If extraction test failed, bug is in extraction/integration")
        else:
            print("\n❌ Basic commitment lifecycle is broken")
            print("   Bug is in core tracker logic")

    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
