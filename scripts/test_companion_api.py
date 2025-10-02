#!/usr/bin/env python3
"""Test script for PMM Companion API endpoints."""

import os
import sys

import requests

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

BASE_URL = "http://localhost:8001"
TEST_DB = "tests/data/reflections_and_identity.db"


def check_endpoint(name: str, url: str, expected_keys: list = None) -> bool:
    """Test a single API endpoint."""
    try:
        print(f"\n🧪 Testing {name}...")
        response = requests.get(url, timeout=5)

        if response.status_code != 200:
            print(f"❌ Failed: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

        data = response.json()

        # Check version field
        if "version" not in data:
            print("❌ Missing version field")
            return False

        print(f"✅ Success: HTTP 200, Version {data['version']}")

        # Check expected keys
        if expected_keys:
            for key in expected_keys:
                if key not in data:
                    print(f"⚠️  Missing expected key: {key}")
                else:
                    value = data[key]
                    if isinstance(value, list):
                        print(f"   {key}: {len(value)} items")
                    elif isinstance(value, dict):
                        print(f"   {key}: {len(value)} fields")
                    else:
                        print(f"   {key}: {value}")

        return True

    except requests.exceptions.ConnectionError:
        print(f"❌ Connection failed - is server running on {BASE_URL}?")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Run all API endpoint tests."""
    print("🚀 PMM Companion API Test Suite")
    print(f"Server: {BASE_URL}")
    print(f"Test DB: {TEST_DB}")

    tests = [
        (
            "GET /events",
            f"{BASE_URL}/events?db={TEST_DB}&limit=5",
            ["events", "pagination"],
        ),
        (
            "GET /events (filtered)",
            f"{BASE_URL}/events?db={TEST_DB}&kind=autonomy_tick&limit=3",
            ["events"],
        ),
        ("GET /metrics", f"{BASE_URL}/metrics?db={TEST_DB}", ["metrics"]),
        (
            "GET /reflections",
            f"{BASE_URL}/reflections?db={TEST_DB}&limit=3",
            ["reflections", "count"],
        ),
        (
            "GET /commitments",
            f"{BASE_URL}/commitments?db={TEST_DB}&status=open&limit=3",
            ["commitments", "count"],
        ),
        (
            "GET /commitments (all)",
            f"{BASE_URL}/commitments?db={TEST_DB}&status=all&limit=5",
            ["commitments"],
        ),
    ]

    results = []
    for name, url, expected_keys in tests:
        success = check_endpoint(name, url, expected_keys)
        results.append((name, success))

    # Summary
    print("\n📊 Test Results:")
    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {status} {name}")

    print(f"\n🎯 Summary: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! API is ready for Phase 2.")
    else:
        print("⚠️  Some tests failed. Check server status and logs.")
        sys.exit(1)


if __name__ == "__main__":
    main()
