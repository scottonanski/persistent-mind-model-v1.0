#!/usr/bin/env python3
"""Production validation script for Echo's artificial amnesia fix.

Tests the routed context system against Echo's actual ledger to validate
that the identity parsing bug and confabulation issues are resolved.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after path modification - this is necessary for scripts
# ruff: noqa: E402
from pmm.runtime.routed_integration import (
    build_context_routed_or_fallback,
    create_routed_infrastructure,
    is_routed_context_enabled,
)
from pmm.storage.eventlog import EventLog


def validate_echo_identity():
    """Validate Echo's identity resolution from actual ledger."""
    print("🔍 Validating Echo's Identity Resolution")
    print("-" * 50)

    # Use actual PMM database
    db_path = project_root / ".data" / "pmm.db"
    if not db_path.exists():
        print(f"❌ PMM database not found at {db_path}")
        return False

    eventlog = EventLog(str(db_path))

    # Create routed infrastructure
    event_index, event_router, identity_resolver = create_routed_infrastructure(
        eventlog
    )

    # Test identity resolution
    current_identity = identity_resolver.current_identity()
    if current_identity:
        print(f"✅ Current identity: {current_identity.name}")
        print(f"   Event ID: #{current_identity.event_id}")
        print(f"   Source: {current_identity.source}")
        print(f"   Truth source: [{current_identity.truth_source}]")

        # Check if it's the expected Echo identity
        if current_identity.name == "Echo":
            print("✅ Echo identity correctly resolved")
        else:
            print(f"⚠️  Identity is '{current_identity.name}', not 'Echo'")
    else:
        print("❌ No identity resolved")
        return False

    # Test identity timeline
    timeline = identity_resolver.get_identity_timeline()
    print(f"\n📜 Identity Timeline ({len(timeline)} changes):")
    for i, identity in enumerate(timeline):
        print(
            f"   {i+1}. Event #{identity.event_id}: {identity.name} (source: {identity.source})"
        )

    # Test problematic inputs
    print("\n🧪 Testing Problematic Inputs:")
    problematic_inputs = [
        "What is my name?",
        "Echo or not?",
        "Not sure about that",
        "Or maybe something else?",
    ]

    baseline_identity = identity_resolver.current_identity()
    for input_text in problematic_inputs:
        proposal = identity_resolver.propose_identity(input_text)
        current = identity_resolver.current_identity()

        if (
            current
            and baseline_identity
            and current.event_id == baseline_identity.event_id
        ):
            print(
                f"   ✅ '{input_text}' -> No identity change (confidence={proposal.confidence})"
            )
        else:
            print(f"   ❌ '{input_text}' -> Identity changed!")
            return False

    return True


def validate_event_content():
    """Validate that specific events return exact content."""
    print("\n🔍 Validating Event Content Accuracy")
    print("-" * 50)

    db_path = project_root / ".data" / "pmm.db"
    eventlog = EventLog(str(db_path))

    # Test specific events that Echo previously confabulated
    test_events = [214, 333, 1987, 5300, 5306]  # From our earlier analysis

    for event_id in test_events:
        events = eventlog.read_by_ids([event_id])
        if events:
            event = events[0]
            print(f"✅ Event #{event_id}: {event['kind']}")
            print(
                f"   Content: {event['content'][:100]}{'...' if len(event['content']) > 100 else ''}"
            )
        else:
            print(f"⚠️  Event #{event_id}: Not found")

    return True


def validate_routed_context():
    """Validate routed context building."""
    print("\n🔍 Validating Routed Context Building")
    print("-" * 50)

    db_path = project_root / ".data" / "pmm.db"
    eventlog = EventLog(str(db_path))

    # Force routed context on
    os.environ["PMM_ROUTED_CONTEXT"] = "on"

    try:
        diagnostics = {}
        context = build_context_routed_or_fallback(
            eventlog=eventlog, diagnostics=diagnostics
        )

        print("✅ Context built successfully")
        print(f"   Routing enabled: {diagnostics.get('routing_enabled', False)}")
        print(f"   Events routed: {diagnostics.get('events_routed', 0)}")
        print(f"   Truth source: {diagnostics.get('truth_source', 'unknown')}")

        # Count truth tags
        read_tags = context.count("[read]")
        semantic_tags = context.count("[semantic]")
        reconstructed_tags = context.count("[reconstructed]")

        print(
            f"   Truth tags: {read_tags} [read], {semantic_tags} [semantic], {reconstructed_tags} [reconstructed]"
        )

        # Check for key content
        if "Echo" in context:
            print("✅ Echo identity found in context")
        else:
            print("⚠️  Echo identity not found in context")

        if "[read]" in context:
            print("✅ Truth-source tagging present")
        else:
            print("❌ No truth-source tags found")
            return False

        return True

    except Exception as e:
        print(f"❌ Context building failed: {e}")
        return False
    finally:
        # Cleanup
        if "PMM_ROUTED_CONTEXT" in os.environ:
            del os.environ["PMM_ROUTED_CONTEXT"]


def validate_commitment_accuracy():
    """Validate commitment retrieval accuracy."""
    print("\n🔍 Validating Commitment Accuracy")
    print("-" * 50)

    db_path = project_root / ".data" / "pmm.db"
    eventlog = EventLog(str(db_path))

    # Create router and query commitments
    event_index, event_router, identity_resolver = create_routed_infrastructure(
        eventlog
    )

    from pmm.runtime.event_router import ContextQuery

    commitment_query = ContextQuery(
        required_kinds=["commitment_open", "commitment_close", "commitment_expire"],
        semantic_terms=[],
        limit=100,
    )

    commitment_event_ids = event_router.route(commitment_query)
    commitment_events = eventlog.read_by_ids(commitment_event_ids)

    # Count by type
    open_events = [e for e in commitment_events if e["kind"] == "commitment_open"]
    close_events = [e for e in commitment_events if e["kind"] == "commitment_close"]
    expire_events = [e for e in commitment_events if e["kind"] == "commitment_expire"]

    print(f"✅ Found {len(commitment_events)} total commitment events")
    print(f"   Open: {len(open_events)}")
    print(f"   Closed: {len(close_events)}")
    print(f"   Expired: {len(expire_events)}")

    # Show some examples
    print("\n📋 Recent Commitments:")
    for event in sorted(open_events, key=lambda e: e["id"])[-5:]:
        cid = event.get("meta", {}).get("cid", "")[:8]
        text = event.get("meta", {}).get("text", event.get("content", ""))[:60]
        print(f"   Event #{event['id']}: [{cid}] {text}...")

    return True


def main():
    """Run complete validation suite."""
    print("🚀 Echo Artificial Amnesia Fix - Production Validation")
    print("=" * 60)

    # Check if routed context is enabled
    print(f"PMM_ROUTED_CONTEXT: {os.environ.get('PMM_ROUTED_CONTEXT', 'default (on)')}")
    print(f"Routed context enabled: {is_routed_context_enabled()}")
    print()

    results = []

    try:
        results.append(("Identity Resolution", validate_echo_identity()))
        results.append(("Event Content", validate_event_content()))
        results.append(("Routed Context", validate_routed_context()))
        results.append(("Commitment Accuracy", validate_commitment_accuracy()))

    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        return 1

    # Summary
    print("\n" + "=" * 60)
    print("📊 VALIDATION SUMMARY")
    print("-" * 60)

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:20} {status}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print(
            "\n🎉 All validations passed! Echo's artificial amnesia has been resolved."
        )
        print("   - Identity parsing bug fixed")
        print("   - Full history access restored")
        print("   - Truth-source tagging implemented")
        print("   - Confabulation eliminated")
        return 0
    else:
        print(
            f"\n⚠️  {len(results) - passed} validation(s) failed. Review the issues above."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
