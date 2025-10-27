#!/usr/bin/env python3
"""
Heartbeat Validation Test
========================

This script validates that the autonomy_tick emission is working correctly
after restoring the missing heartbeat to the PMM system.

It creates a minimal runtime, runs a single tick, and verifies:
1. autonomy_tick event is emitted
2. Telemetry contains IAS/GAS values
3. Stage and reflection status are recorded
4. Tick number is correct
5. Source is "AutonomyLoop"
"""

import tempfile
from pathlib import Path

from pmm.llm.factory import LLMConfig
from pmm.runtime.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, Runtime


def test_heartbeat_emission():
    """Test that autonomy_tick events are properly emitted with full telemetry."""
    print("🔍 Testing autonomy_tick heartbeat emission...")

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Initialize minimal runtime
        cfg = LLMConfig(provider="dummy", model="test")
        eventlog = EventLog(db_path)
        runtime = Runtime(cfg, eventlog)

        # Mock the reflect method to avoid LLM calls
        runtime.reflect = lambda context: "Test reflection for heartbeat validation"

        # Create autonomy loop with short interval
        loop = AutonomyLoop(
            eventlog=eventlog,
            cooldown=runtime.cooldown,
            interval_seconds=0.1,
            runtime=runtime,
            bootstrap_identity=False,
        )

        # Get initial event count
        initial_events = eventlog.read_all()
        initial_count = len(initial_events)
        initial_autonomy_ticks = sum(
            1 for ev in initial_events if ev.get("kind") == "autonomy_tick"
        )

        print(
            f"📊 Initial state: {initial_count} events, {initial_autonomy_ticks} autonomy_tick events"
        )

        # Run a single tick
        print("⚡ Running single autonomy tick...")
        loop.tick()

        # Check results
        final_events = eventlog.read_all()
        final_count = len(final_events)

        # Find the autonomy_tick event
        autonomy_tick_events = [
            ev for ev in final_events if ev.get("kind") == "autonomy_tick"
        ]
        final_autonomy_ticks = len(autonomy_tick_events)

        print(
            f"📊 Final state: {final_count} events, {final_autonomy_ticks} autonomy_tick events"
        )

        # Validation checks
        success = True

        # Check 1: autonomy_tick event was emitted
        if final_autonomy_ticks <= initial_autonomy_ticks:
            print("❌ FAIL: No new autonomy_tick event was emitted")
            success = False
        else:
            print("✅ PASS: autonomy_tick event was emitted")

        # Check 2: Get the latest autonomy_tick event
        if autonomy_tick_events:
            latest_tick = autonomy_tick_events[-1]
            meta = latest_tick.get("meta", {})

            # Check telemetry structure
            telemetry = meta.get("telemetry", {})
            if "IAS" in telemetry and "GAS" in telemetry:
                print(
                    f"✅ PASS: Telemetry contains IAS={telemetry['IAS']}, GAS={telemetry['GAS']}"
                )
            else:
                print("❌ FAIL: Missing IAS/GAS in telemetry")
                success = False

            # Check stage info
            if "stage" in meta:
                print(f"✅ PASS: Stage recorded as '{meta['stage']}'")
            else:
                print("❌ FAIL: Missing stage information")
                success = False

            # Check reflection status
            reflect_info = meta.get("reflect", {})
            if "did" in reflect_info and "reason" in reflect_info:
                print(
                    f"✅ PASS: Reflection status: did={reflect_info['did']}, reason='{reflect_info['reason']}'"
                )
            else:
                print("❌ FAIL: Missing reflection status")
                success = False

            # Check source
            if meta.get("source") == "AutonomyLoop":
                print("✅ PASS: Source correctly set to 'AutonomyLoop'")
            else:
                print(f"❌ FAIL: Wrong source: {meta.get('source')}")
                success = False

            # Check tick number
            if "tick" in meta:
                print(f"✅ PASS: Tick number recorded as {meta['tick']}")
            else:
                print("❌ FAIL: Missing tick number")
                success = False

            # Check timestamp
            if "timestamp" in meta:
                timestamp = meta["timestamp"]
                if isinstance(timestamp, (int, float)) and timestamp > 0:
                    print(f"✅ PASS: Timestamp recorded as {timestamp}")
                else:
                    print(f"❌ FAIL: Invalid timestamp: {timestamp}")
                    success = False
            else:
                print("❌ FAIL: Missing timestamp")
                success = False

            # Print full event for inspection
            print("\n📋 Full autonomy_tick event:")
            print(f"   ID: {latest_tick.get('id')}")
            print(f"   Kind: {latest_tick.get('kind')}")
            print(f"   Content: '{latest_tick.get('content')}'")
            print(f"   Meta keys: {list(meta.keys())}")

        else:
            print("❌ FAIL: No autonomy_tick events found")
            success = False

        # Final result
        if success:
            print("\n🎉 HEARTBEAT VALIDATION SUCCESSFUL!")
            print("   The autonomy_tick emission is working correctly.")
            print("   The system's awareness rhythm has been restored.")
            assert True  # Test passes
        else:
            print("\n💔 HEARTBEAT VALIDATION FAILED!")
            print("   The autonomy_tick emission needs further debugging.")
            assert False, "Heartbeat validation failed"

    finally:
        # Cleanup
        try:
            Path(db_path).unlink()
        except Exception:
            pass


if __name__ == "__main__":
    success = test_heartbeat_emission()
    exit(0 if success else 1)
