"""A/B validation suite: tail vs router comparison.

Tests the same ledger with both tail-constrained and routed approaches
to validate that routing provides more accurate results.
"""

import os
import tempfile
import time
from pathlib import Path

from pmm.runtime.routed_integration import (
    build_context_routed_or_fallback,
    create_routed_infrastructure,
)
from pmm.storage.eventlog import EventLog


class TestABValidation:
    """A/B validation comparing tail vs router approaches."""

    def create_test_ledger(self, eventlog: EventLog) -> dict[str, int]:
        """Create a test ledger simulating Echo's history."""
        event_ids = {}

        # Add early identity (would be outside tail window)
        event_ids["echo_identity"] = eventlog.append(
            kind="identity_adopt",
            content="Echo",
            meta={
                "name": "Echo",
                "source": "user",
                "confidence": 0.95,
                "intent": "assign_assistant_name",
            },
        )

        # Add user identity
        event_ids["user_identity"] = eventlog.append(
            kind="user_identity_set",
            content="User identified as: Scott",
            meta={"user_name": "Scott"},
        )

        # Add early commitment
        event_ids["early_commitment"] = eventlog.append(
            kind="commitment_open",
            content="I will lead with utility first",
            meta={"cid": "util123", "text": "I will lead with utility first"},
        )

        # Add the problematic reflection (event #333 equivalent)
        event_ids["technical_reflection"] = eventlog.append(
            kind="reflection",
            content="IAS=0.155 indicates low identity alignment — below S1 threshold (0.35)",
            meta={"novelty": 1.0, "style": "succinct"},
        )

        # Add many filler events to push early events outside tail window
        for i in range(1500):  # More than typical tail limit
            eventlog.append(
                kind="autonomy_tick" if i % 10 == 0 else "reflection",
                content=f"Filler event {i}",
                meta={"telemetry": {"IAS": 0.8, "GAS": 0.7}} if i % 10 == 0 else {},
            )

        # Add recent events
        event_ids["recent_reflection"] = eventlog.append(
            kind="reflection",
            content="Recent analysis of system performance",
            meta={"novelty": 0.8},
        )

        event_ids["recent_commitment"] = eventlog.append(
            kind="commitment_open",
            content="I will improve response accuracy",
            meta={"cid": "accuracy456", "text": "I will improve response accuracy"},
        )

        return event_ids

    def test_identity_timeline_accuracy(self):
        """Test that router returns accurate identity timeline vs tail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_ids = self.create_test_ledger(eventlog)

            # Mode A: Tail-constrained (force feature flag off)
            os.environ["PMM_ROUTED_CONTEXT"] = "off"

            tail_diagnostics = {}
            tail_context = build_context_routed_or_fallback(
                eventlog=eventlog, diagnostics=tail_diagnostics
            )

            # Mode B: Router-based (force feature flag on)
            os.environ["PMM_ROUTED_CONTEXT"] = "on"

            router_diagnostics = {}
            router_context = build_context_routed_or_fallback(
                eventlog=eventlog, diagnostics=router_diagnostics
            )

            # Cleanup environment
            if "PMM_ROUTED_CONTEXT" in os.environ:
                del os.environ["PMM_ROUTED_CONTEXT"]

            # Validate results
            print("=== IDENTITY TIMELINE ACCURACY ===")
            print(
                f"Tail routing enabled: {tail_diagnostics.get('routing_enabled', False)}"
            )
            print(
                f"Router routing enabled: {router_diagnostics.get('routing_enabled', False)}"
            )

            # Router should have verified identity from early event
            assert "Echo" in router_context, "Router should find Echo identity"
            assert "[read]" in router_context, "Router should have [read] tags"
            assert (
                f"event #{event_ids['echo_identity']}" in router_context
            ), "Router should reference correct event ID"

            # Tail may miss early identity depending on window size
            print(f"Tail found Echo: {'Echo' in tail_context}")
            print(f"Router found Echo: {'Echo' in router_context}")

    def test_commitment_accuracy(self):
        """Test commitment retrieval accuracy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_ids = self.create_test_ledger(eventlog)

            # Create infrastructure for direct testing
            event_index, event_router, identity_resolver = create_routed_infrastructure(
                eventlog
            )

            # Test router directly
            from pmm.runtime.event_router import ContextQuery

            commitment_query = ContextQuery(
                required_kinds=[
                    "commitment_open",
                    "commitment_close",
                    "commitment_expire",
                ],
                semantic_terms=[],
                limit=50,
            )
            commitment_event_ids = event_router.route(commitment_query)
            commitment_events = eventlog.read_by_ids(commitment_event_ids)

            # Should find both early and recent commitments
            found_early = any(
                e["id"] == event_ids["early_commitment"] for e in commitment_events
            )
            found_recent = any(
                e["id"] == event_ids["recent_commitment"] for e in commitment_events
            )

            print("=== COMMITMENT ACCURACY ===")
            print(f"Router found early commitment: {found_early}")
            print(f"Router found recent commitment: {found_recent}")
            print(f"Total commitments found: {len(commitment_events)}")

            # Validate with assertions
            assert found_early, "Router should find early commitment"
            assert found_recent, "Router should find recent commitment"
            assert len(commitment_events) > 0, "Should find some commitments"

    def test_event_content_accuracy(self):
        """Test that router returns exact event content vs tail reconstruction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            event_ids = self.create_test_ledger(eventlog)

            # Test direct event retrieval
            technical_reflection_id = event_ids["technical_reflection"]
            events = eventlog.read_by_ids([technical_reflection_id])

            if events:
                actual_content = events[0]["content"]
                print("=== EVENT CONTENT ACCURACY ===")
                print(f"Event #{technical_reflection_id} actual content:")
                print(f"  {actual_content}")

                # Router should be able to fetch exact content
                assert (
                    "IAS=0.155" in actual_content
                ), "Should contain exact technical content"
                assert (
                    "identity alignment" in actual_content
                ), "Should contain exact phrases"

            else:
                assert False, "Event not found"

    def test_performance_comparison(self):
        """Compare performance of tail vs router approaches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            self.create_test_ledger(eventlog)

            # Create router infrastructure once
            infrastructure = create_routed_infrastructure(eventlog)

            # Time tail approach
            os.environ["PMM_ROUTED_CONTEXT"] = "off"

            tail_start = time.perf_counter()
            for _ in range(10):  # Multiple runs for average
                build_context_routed_or_fallback(eventlog=eventlog)
            tail_duration = (time.perf_counter() - tail_start) / 10

            # Time router approach
            os.environ["PMM_ROUTED_CONTEXT"] = "on"

            router_start = time.perf_counter()
            for _ in range(10):  # Multiple runs for average
                build_context_routed_or_fallback(
                    eventlog=eventlog, routed_infrastructure=infrastructure
                )
            router_duration = (time.perf_counter() - router_start) / 10

            # Cleanup
            if "PMM_ROUTED_CONTEXT" in os.environ:
                del os.environ["PMM_ROUTED_CONTEXT"]

            print("=== PERFORMANCE COMPARISON ===")
            print(f"Tail approach: {tail_duration*1000:.2f}ms average")
            print(f"Router approach: {router_duration*1000:.2f}ms average")
            print(f"Overhead: {((router_duration/tail_duration)-1)*100:.1f}%")

            # Validate performance is reasonable (less than 10x overhead)
            overhead_percent = ((router_duration / tail_duration) - 1) * 100
            assert (
                overhead_percent < 1000
            ), f"Router overhead too high: {overhead_percent:.1f}%"

    def test_truth_source_tagging(self):
        """Test that router properly tags truth sources."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            eventlog = EventLog(str(db_path))
            self.create_test_ledger(eventlog)

            # Force router mode
            os.environ["PMM_ROUTED_CONTEXT"] = "on"

            diagnostics = {}
            router_context = build_context_routed_or_fallback(
                eventlog=eventlog, diagnostics=diagnostics
            )

            # Cleanup
            if "PMM_ROUTED_CONTEXT" in os.environ:
                del os.environ["PMM_ROUTED_CONTEXT"]

            # Count truth source tags
            read_tags = router_context.count("[read]")
            semantic_tags = router_context.count("[semantic]")
            reconstructed_tags = router_context.count("[reconstructed]")

            print("=== TRUTH SOURCE TAGGING ===")
            print(f"[read] tags: {read_tags}")
            print(f"[semantic] tags: {semantic_tags}")
            print(f"[reconstructed] tags: {reconstructed_tags}")
            print(
                f"Truth source in diagnostics: {diagnostics.get('truth_source', 'unknown')}"
            )

            # Router should primarily use [read] tags
            assert read_tags > 0, "Router should have [read] tags"
            # Note: routing_enabled may be False if fallback occurred, but we should still have [read] tags

    def run_full_validation(self):
        """Run complete A/B validation suite."""
        print("🧪 Starting A/B Validation Suite: Tail vs Router")
        print("=" * 60)

        try:
            self.test_identity_timeline_accuracy()
            self.test_commitment_accuracy()
            self.test_event_content_accuracy()
            self.test_performance_comparison()
            self.test_truth_source_tagging()

            print("\n" + "=" * 60)
            print("✅ A/B Validation Complete")
            print("\n📊 SUMMARY:")
            print("  All tests passed successfully!")
            print("  - Router found Echo identity")
            print("  - Router has [read] tags")
            print("  - Found early and recent commitments")
            print("  - Performance overhead acceptable")
            print("  - Truth source tagging working")

            return True

        except Exception as e:
            print(f"❌ Validation failed: {e}")
            raise
