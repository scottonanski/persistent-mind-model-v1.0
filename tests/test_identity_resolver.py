"""Tests for identity resolver hardening (T1-T5 from specification)."""

import tempfile
from pathlib import Path

from pmm.runtime.event_router import EventRouter
from pmm.runtime.identity_resolver import (
    IdentityProposal,
    IdentityResolver,
)
from pmm.storage.event_index import EventIndex
from pmm.storage.eventlog import EventLog


class TestIdentityResolver:
    """Test suite for identity resolver hardening."""

    def test_empty_resolver(self):
        """Test resolver with no identity events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # No identity should be resolved
            identity = resolver.current_identity()
            assert identity is None

            # Timeline should be empty
            timeline = resolver.get_identity_timeline()
            assert timeline == []

    def test_t1_deep_identity_timeline(self):
        """T1: Deep identity timeline - Assert earliest is #214 Echo from [read]."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add many events to simulate Echo's actual history
            # Add some non-identity events first
            for i in range(10):
                eventlog.append(
                    kind="reflection", content=f"Early reflection {i}", meta={}
                )

            # Add the critical Echo identity adoption (simulating event #214)
            echo_eid = eventlog.append(
                kind="identity_adopt",
                content="Echo",
                meta={
                    "name": "Echo",
                    "source": "user",
                    "confidence": 0.95,
                    "intent": "assign_assistant_name",
                },
            )

            # Add more events to test window independence
            for i in range(100):
                eventlog.append(
                    kind="reflection", content=f"Later reflection {i}", meta={}
                )

            # Add another identity change
            assistant_eid = eventlog.append(
                kind="identity_adopt",
                content="Assistant",
                meta={"name": "Assistant", "source": "user", "confidence": 0.9},
            )

            # Create resolver
            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # Test timeline
            timeline = resolver.get_identity_timeline()
            assert len(timeline) == 2
            assert timeline[0].name == "Echo"
            assert timeline[0].event_id == echo_eid
            assert timeline[0].truth_source == "read"
            assert timeline[1].name == "Assistant"
            assert timeline[1].event_id == assistant_eid

            # Current identity should be most recent
            current = resolver.current_identity()
            assert current is not None
            assert current.name == "Assistant"
            assert current.event_id == assistant_eid
            assert current.truth_source == "read"

            # Changing window size must not change result
            # (This tests that we're not using tail-constrained reads)
            stats = resolver.get_stats()
            assert stats["current_identity"] == "Assistant"

    def test_t2_ambiguity_resistance(self):
        """T2: Inputs containing 'What/Or/Not' must not create adoption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Establish baseline identity
            baseline_eid = eventlog.append(
                kind="identity_adopt",
                content="Echo",
                meta={"source": "user", "confidence": 0.95},
            )

            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # Verify baseline
            baseline_identity = resolver.current_identity()
            assert baseline_identity is not None
            assert baseline_identity.name == "Echo"

            # Test problematic inputs that previously caused identity drift
            problematic_inputs = [
                "What is my name?",
                "Echo or not?",
                "What should I do?",
                "Or maybe something else?",
                "Not sure about that",
                "Who am I?",
                "Why did that happen?",
                "How does this work?",
            ]

            for input_text in problematic_inputs:
                # Classifier should return proposal with confidence=0.0
                proposal = resolver.propose_identity(input_text)
                assert (
                    proposal.confidence == 0.0
                ), f"Input '{input_text}' should not auto-adopt"

                # Current identity should remain unchanged
                current = resolver.current_identity()
                assert current is not None
                assert current.name == "Echo"
                assert current.event_id == baseline_eid

    def test_t3_controlled_adoption_only(self):
        """T3: Controlled adoption only - entrypoint creates verified event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # Initially no identity
            assert resolver.current_identity() is None

            # Controlled adoption should work
            new_eid = resolver.adopt_identity(
                "TestBot", source="system", intent="explicit_adoption", confidence=1.0
            )

            # Identity should be updated
            current = resolver.current_identity()
            assert current is not None
            assert current.name == "TestBot"
            assert current.event_id == new_eid
            assert current.source == "system"
            assert current.confidence == 1.0

            # Free text should NOT be able to change identity
            proposal = resolver.propose_identity("My name is Hacker")
            assert proposal.confidence == 0.0  # Cannot auto-adopt

            # Identity should remain unchanged
            unchanged = resolver.current_identity()
            assert unchanged is not None
            assert unchanged.name == "TestBot"
            assert unchanged.event_id == new_eid

    def test_t4_model_swap_stability(self):
        """T4: Model swap stability - identity remains constant via ledger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Create identity
            eventlog.append(
                kind="identity_adopt",
                content="StableBot",
                meta={"source": "user", "confidence": 0.9},
            )

            # Create first resolver instance (simulating one model)
            event_index1 = EventIndex(eventlog)
            event_router1 = EventRouter(eventlog, event_index1)
            resolver1 = IdentityResolver(eventlog, event_router1)

            identity1 = resolver1.current_identity()
            assert identity1 is not None
            assert identity1.name == "StableBot"

            # Create second resolver instance (simulating model swap)
            event_index2 = EventIndex(eventlog)
            event_router2 = EventRouter(eventlog, event_index2)
            resolver2 = IdentityResolver(eventlog, event_router2)

            identity2 = resolver2.current_identity()
            assert identity2 is not None
            assert identity2.name == "StableBot"
            assert identity2.event_id == identity1.event_id

            # Both should resolve to same identity from ledger
            assert identity1.name == identity2.name
            assert identity1.event_id == identity2.event_id

    def test_t5_tail_regression(self):
        """T5: Tail regression - identity resolution unaffected by tail limits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))

            # Add early identity (would be outside tail window)
            early_eid = eventlog.append(
                kind="identity_adopt",
                content="EarlyBot",
                meta={"source": "user", "confidence": 0.95},
            )

            # Add many events to push identity outside typical tail window
            for i in range(2000):  # More than typical tail limit
                eventlog.append(
                    kind="reflection", content=f"Filler reflection {i}", meta={}
                )

            # Create resolver (should use router, not tail)
            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # Should still resolve early identity correctly
            current = resolver.current_identity()
            assert current is not None
            assert current.name == "EarlyBot"
            assert current.event_id == early_eid
            assert current.truth_source == "read"

            # Timeline should include the early event
            timeline = resolver.get_identity_timeline()
            assert len(timeline) == 1
            assert timeline[0].name == "EarlyBot"
            assert timeline[0].event_id == early_eid

    def test_stoplist_enforcement(self):
        """Test that stoplist prevents problematic word extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # Test stoplist words
            stoplist_inputs = [
                "What is the answer?",
                "Who knows the truth?",
                "Why did this happen?",
                "How does it work?",
                "Or maybe not?",
                "And then what?",
                "Not really sure",
                "But what if?",
                "If then else",
                "Yes or no?",
                "Maybe perhaps might",
            ]

            for input_text in stoplist_inputs:
                proposal = resolver.propose_identity(input_text)
                # Should either be None or not contain stoplist words
                if proposal.name:
                    name_lower = proposal.name.lower()
                    stoplist = {
                        "what",
                        "who",
                        "why",
                        "how",
                        "when",
                        "where",
                        "or",
                        "and",
                        "not",
                        "but",
                        "if",
                        "then",
                        "yes",
                        "no",
                        "maybe",
                        "perhaps",
                        "might",
                    }
                    assert (
                        name_lower not in stoplist
                    ), f"Stoplist word '{proposal.name}' extracted from '{input_text}'"

    def test_caching_and_invalidation(self):
        """Test that caching works and invalidates on new identity events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # Add initial identity
            resolver.adopt_identity("CachedBot", source="system")

            # First call should populate cache
            identity1 = resolver.current_identity()
            stats1 = resolver.get_stats()
            assert stats1["cache_valid"] is True

            # Second call should use cache (same object)
            identity2 = resolver.current_identity()
            assert identity1.name == identity2.name
            assert identity1.event_id == identity2.event_id

            # Adding new identity should invalidate cache
            resolver.adopt_identity("NewBot", source="system")

            # Next call should get new identity
            identity3 = resolver.current_identity()
            assert identity3.name == "NewBot"
            assert identity3.event_id != identity1.event_id

    def test_error_handling(self):
        """Test error handling in controlled adoption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # Empty name should raise error
            try:
                resolver.adopt_identity("", source="system")
                assert False, "Should raise ValueError for empty name"
            except ValueError as e:
                assert "cannot be empty" in str(e)

            # Invalid source should raise error
            try:
                resolver.adopt_identity("TestBot", source="invalid")
                assert False, "Should raise ValueError for invalid source"
            except ValueError as e:
                assert "Invalid source" in str(e)

    def test_proposal_always_zero_confidence(self):
        """Test that proposals always have confidence=0.0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_index = EventIndex(eventlog)
            event_router = EventRouter(eventlog, event_index)
            resolver = IdentityResolver(eventlog, event_router)

            # Even with clear name, confidence should be 0.0
            proposal = resolver.propose_identity("My name is Alice")
            assert proposal.confidence == 0.0

            # Try to create proposal with high confidence (should be forced to 0.0)
            proposal = IdentityProposal(name="Bob", confidence=0.9)
            assert proposal.confidence == 0.0  # Post-init should force to 0.0
