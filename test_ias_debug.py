#!/usr/bin/env python3
"""
Test script to debug IAS computation with detailed logging.
This script will create some test events and trigger IAS computation to see the logging.
"""

import logging
import os
import sys

from pmm.storage.eventlog import EventLog
from pmm.runtime.metrics import get_or_compute_ias_gas

# Add the pmm module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging to see our debug messages
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def test_ias_computation():
    """Test IAS computation with various confidence levels."""

    # Create a temporary in-memory database
    eventlog = EventLog(":memory:")

    print("=== Testing IAS Computation with Different Confidence Levels ===\n")

    # Test Case 1: Low confidence adoption (should be ignored)
    print("1. Testing low confidence adoption (0.5)...")
    eventlog.append(
        "identity_adopt", "Persistent", {"sanitized": "Persistent", "confidence": 0.5}
    )

    # Add some autonomy ticks
    for i in range(8):
        eventlog.append("autonomy_tick", "", {})

    ias, gas = get_or_compute_ias_gas(eventlog)
    print(f"Result: IAS={ias:.4f}, GAS={gas:.4f}\n")

    # Test Case 2: High confidence adoption (should be accepted)
    print("2. Testing high confidence adoption (0.95)...")
    eventlog.append(
        "identity_adopt", "Persistent", {"sanitized": "Persistent", "confidence": 0.95}
    )

    # Add more autonomy ticks to trigger stability bonuses
    for i in range(12):
        eventlog.append("autonomy_tick", "", {})

    ias, gas = get_or_compute_ias_gas(eventlog)
    print(f"Result: IAS={ias:.4f}, GAS={gas:.4f}\n")

    # Test Case 3: Missing confidence (defaults to 0.0, should be ignored)
    print("3. Testing missing confidence (defaults to 0.0)...")
    eventlog.append(
        "identity_adopt",
        "TestName",
        {
            "sanitized": "TestName"
            # No confidence field
        },
    )

    for i in range(5):
        eventlog.append("autonomy_tick", "", {})

    ias, gas = get_or_compute_ias_gas(eventlog)
    print(f"Result: IAS={ias:.4f}, GAS={gas:.4f}\n")

    print("=== Test completed ===")
    print("Check the logs above to see which adoptions were accepted vs ignored.")


if __name__ == "__main__":
    test_ias_computation()
