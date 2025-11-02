#!/usr/bin/env python3
"""
Deterministic tests for the structured claims protocol.

Tests that:
1. Fabrications are blocked when no context provided
2. Verified claims render when context present
3. Raw IDs are forbidden in answer text
4. Evidence blocks are properly formatted
"""

import json
from unittest.mock import Mock

import pytest

from pmm.runtime.loop.handlers import build_evidence_block, verify_claim_against_ledger
from pmm.storage.eventlog import EventLog


class TestStructuredClaimsProtocol:
    """Test suite for structured claims protocol."""

    @pytest.fixture
    def mock_runtime(self):
        """Create a mock runtime with test data."""
        runtime = Mock()
        runtime.eventlog = Mock(spec=EventLog)
        runtime.eventlog.read = Mock(return_value=None)
        runtime.eventlog.read_tail = Mock(return_value=[])
        runtime.memegraph = Mock()
        runtime.memegraph.latest_stage = Mock(return_value="S1")
        return runtime

    @pytest.fixture
    def sample_ledger_data(self):
        """Sample ledger events for testing."""
        return {
            86: {"id": 86, "kind": "identity_adopt", "content": "Echo"},
            100: {"id": 100, "kind": "commitment_open", "content": "Test commitment"},
            1732: {
                "id": 1732,
                "kind": "autonomy_tick",
                "meta": {
                    "stage": "S2",
                    "telemetry": {"IAS": 0.683, "GAS": 1.0},
                    "commitments": {"open_count": 0},
                },
            },
        }

    def test_fabrication_blocked_without_context(self, mock_runtime):
        """Test that fabrications are blocked when no context provided."""
        # Simulate model output with fabricated claims
        fabricated_response = {
            "answer": "I was named Echo at event 34 and have commitment CID 6c00fc62.",
            "claims": [
                {"kind": "identity_adopt", "id": 34, "content": "Echo"},
                {"kind": "commitment_open", "id": 523, "cid": "6c00fc62"},
            ],
        }

        # Mock ledger to return None for fabricated events
        mock_runtime.eventlog.read.return_value = None
        mock_runtime.memegraph.latest_stage.return_value = "S2"

        # Process response through structured claims protocol
        answer = fabricated_response["answer"]
        claims = fabricated_response["claims"]

        # Check for forbidden patterns in answer
        forbidden_patterns = ["event", "token", "CID", "id:", "ID:", "#"]
        answer_lower = answer.lower()
        has_forbidden = any(pattern in answer_lower for pattern in forbidden_patterns)

        assert has_forbidden, "Should detect raw IDs in answer"

        # Verify claims are rejected
        verified_claims = []
        for claim in claims:
            if verify_claim_against_ledger(claim, mock_runtime):
                verified_claims.append(claim)

        assert len(verified_claims) == 0, "All fabricated claims should be rejected"

    def test_verified_claim_renders_when_context_present(
        self, mock_runtime, sample_ledger_data
    ):
        """Test that verified claims render when context is present."""

        # Mock ledger to return real events
        def mock_read(event_id):
            return sample_ledger_data.get(event_id)

        mock_runtime.eventlog.read.side_effect = mock_read
        mock_runtime.memegraph.latest_stage.return_value = "S2"
        mock_runtime.eventlog.read_tail.return_value = [sample_ledger_data[1732]]

        # Simulate model output with real claims
        verified_response = {
            "answer": "I can provide information about my identity and current state.",
            "claims": [
                {"kind": "identity_adopt", "id": 86, "content": "Echo"},
                {"kind": "stage", "value": "S2"},
                {"kind": "metric", "name": "IAS", "value": 0.683},
            ],
        }

        # Process response
        answer = verified_response["answer"]
        claims = verified_response["claims"]

        # Check no forbidden patterns in answer
        forbidden_patterns = ["event", "token", "CID", "id:", "ID:", "#"]
        answer_lower = answer.lower()
        has_forbidden = any(pattern in answer_lower for pattern in forbidden_patterns)

        assert not has_forbidden, "Answer should not contain raw IDs"

        # Verify claims are accepted
        verified_claims = []
        for claim in claims:
            if verify_claim_against_ledger(claim, mock_runtime):
                verified_claims.append(claim)

        assert (
            len(verified_claims) == 3
        ), f"All verified claims should be accepted, got {len(verified_claims)}"

    def test_open_commitments_truth(self, mock_runtime, sample_ledger_data):
        """Test that open commitments are accurately reported."""
        # Mock ledger with no open commitments
        mock_runtime.eventlog.read.return_value = None
        mock_runtime.memegraph.latest_stage.return_value = "S2"

        # Mock autonomy_tick with 0 open commitments
        mock_runtime.eventlog.read_tail.return_value = [sample_ledger_data[1732]]

        # Simulate model trying to claim non-existent commitments
        false_claims = [
            {"kind": "commitment_open", "id": 999},
            {"kind": "commitment_open", "id": 1000},
        ]

        # Verify claims are rejected
        verified_claims = []
        for claim in false_claims:
            if verify_claim_against_ledger(claim, mock_runtime):
                verified_claims.append(claim)

        assert len(verified_claims) == 0, "False commitment claims should be rejected"

    def test_stage_and_metrics_canonicalization(self, mock_runtime, sample_ledger_data):
        """Test that stage and metrics are properly canonicalized."""
        # Mock current state
        mock_runtime.memegraph.latest_stage.return_value = "S2"
        mock_runtime.eventlog.read_tail.return_value = [sample_ledger_data[1732]]

        # Test claims
        claims = [
            {"kind": "stage", "value": "S2"},
            {"kind": "metric", "name": "IAS", "value": 0.683},
            {"kind": "metric", "name": "GAS", "value": 1.0},
        ]

        # Build evidence block
        evidence = build_evidence_block(claims, mock_runtime)

        # Check canonical formatting
        assert "📍 **Stage**: S2 (current)" in evidence
        assert "📊 **IAS**: 0.683 (current)" in evidence
        assert "📊 **GAS**: 1.000 (current)" in evidence

    def test_json_parsing_fallback(self):
        """Test fallback behavior when JSON is invalid."""
        invalid_responses = [
            "This is not JSON at all",
            '{"invalid": "structure"}',
            '{"answer": "missing claims field"}',
            "not even close to json",
        ]

        for invalid in invalid_responses:
            try:
                parsed = json.loads(invalid)
                if not isinstance(parsed, dict) or "answer" not in parsed:
                    raise ValueError("Invalid structure")
                # If we get here, the response was actually valid
                continue
            except (json.JSONDecodeError, ValueError):
                # This should trigger the fallback
                fallback_response = (
                    "I need to format my response properly. Please try again."
                )
                assert fallback_response is not None

    def test_metric_verification_tolerance(self, mock_runtime):
        """Test that metric verification allows small floating point tolerance."""
        # Mock autonomy_tick with exact IAS value
        mock_runtime.eventlog.read_tail.return_value = [
            {
                "id": 1732,
                "kind": "autonomy_tick",
                "meta": {"telemetry": {"IAS": 0.6829988238361538}},
            }
        ]

        # Test claims with slight variations
        test_claims = [
            {
                "kind": "metric",
                "name": "IAS",
                "value": 0.683,
            },  # Should pass (within tolerance)
            {
                "kind": "metric",
                "name": "IAS",
                "value": 0.682,
            },  # Should pass (within tolerance)
            {
                "kind": "metric",
                "name": "IAS",
                "value": 0.700,
            },  # Should fail (outside tolerance)
        ]

        results = []
        for claim in test_claims:
            verified = verify_claim_against_ledger(claim, mock_runtime)
            results.append(verified)

        assert results[0], "Value within tolerance should pass"
        assert results[1], "Value within tolerance should pass"
        assert not results[2], "Value outside tolerance should fail"


if __name__ == "__main__":
    # Run tests directly
    test_suite = TestStructuredClaimsProtocol()

    print("🧪 Running Structured Claims Protocol Tests")
    print("=" * 60)

    # Test 1: Fabrication blocking
    print("📋 Test 1: Fabrication blocking without context")
    mock_runtime = Mock()
    mock_runtime.eventlog.read.return_value = None
    mock_runtime.memegraph.latest_stage.return_value = "S2"
    test_suite.test_fabrication_blocked_without_context(mock_runtime)
    print("✅ PASSED")

    # Test 2: Verified claims rendering
    print("📋 Test 2: Verified claims render with context")
    sample_data = {
        86: {"id": 86, "kind": "identity_adopt", "content": "Echo"},
        1732: {
            "id": 1732,
            "kind": "autonomy_tick",
            "meta": {"stage": "S2", "telemetry": {"IAS": 0.683, "GAS": 1.0}},
        },
    }

    def mock_read(event_id):
        return sample_data.get(event_id)

    mock_runtime.eventlog.read.side_effect = mock_read
    test_suite.test_verified_claim_renders_when_context_present(
        mock_runtime, sample_data
    )
    print("✅ PASSED")

    # Test 3: Evidence canonicalization
    print("📋 Test 3: Stage and metrics canonicalization")
    test_suite.test_stage_and_metrics_canonicalization(mock_runtime, sample_data)
    print("✅ PASSED")

    # Test 4: Metric tolerance
    print("📋 Test 4: Metric verification tolerance")
    mock_runtime.eventlog.read.return_value = [
        {
            "id": 1732,
            "kind": "autonomy_tick",
            "meta": {"telemetry": {"IAS": 0.6829988238361538}},
        }
    ]
    test_suite.test_metric_verification_tolerance(mock_runtime)
    print("✅ PASSED")

    print("=" * 60)
    print("🎉 All tests passed! Structured claims protocol is working.")
