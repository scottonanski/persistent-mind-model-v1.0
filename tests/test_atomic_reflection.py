"""Tests for Atomic Reflection System (pmm/runtime/atomic_reflection.py)."""

import tempfile

from pmm.runtime.atomic_reflection import AtomicReflection
from pmm.storage.eventlog import EventLog


class TestAtomicReflectionAnalyze:
    """Test AtomicReflection.analyze() deterministic analysis."""

    def test_empty_events_returns_zero_analysis(self):
        """Empty event list should return zero analysis."""
        reflector = AtomicReflection()
        analysis = reflector.analyze([])

        expected = {
            "commitment_stats": {
                "opens": 0,
                "closes": 0,
                "close_rate": 0.0,
                "streak": 0,
            },
            "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {"reflection_diversity": 0.0, "emergence_score": 0.0},
            "event_count": 0,
            "window_size": 100,
        }
        assert analysis == expected

    def test_deterministic_analysis_same_events(self):
        """Same input events should produce identical analysis dicts."""
        events = [
            {"kind": "commitment_open", "content": "test commitment 1"},
            {"kind": "commitment_open", "content": "test commitment 2"},
            {"kind": "commitment_close", "content": "test commitment 1"},
            {
                "kind": "trait_update",
                "meta": {"changes": {"openness": 0.05, "conscientiousness": -0.02}},
            },
            {
                "kind": "reflection",
                "content": "analyzing current system state and priorities",
            },
            {
                "kind": "emergence_report",
                "meta": {"metrics": {"composite_score": 0.65}},
            },
        ]

        reflector = AtomicReflection()
        analysis1 = reflector.analyze(events)
        analysis2 = reflector.analyze(events)

        assert analysis1 == analysis2

    def test_commitment_stats_calculation(self):
        """Should correctly calculate commitment statistics."""
        events = [
            {"kind": "commitment_open", "content": "commit 1"},
            {"kind": "commitment_open", "content": "commit 2"},
            {"kind": "commitment_open", "content": "commit 3"},
            {"kind": "commitment_close", "content": "commit 1"},
            {"kind": "commitment_close", "content": "commit 2"},
        ]

        reflector = AtomicReflection()
        analysis = reflector.analyze(events)

        stats = analysis["commitment_stats"]
        assert stats["opens"] == 3
        assert stats["closes"] == 2
        assert abs(stats["close_rate"] - (2 / 3)) < 0.001
        assert stats["streak"] == 2  # Two consecutive closes at end

    def test_trait_deltas_calculation(self):
        """Should correctly calculate trait drift averages."""
        events = [
            {
                "kind": "trait_update",
                "meta": {"changes": {"openness": 0.05, "conscientiousness": -0.02}},
            },
            {
                "kind": "trait_update",
                "meta": {"changes": {"openness": 0.03, "extraversion": 0.01}},
            },
            {"kind": "trait_update", "meta": {"changes": {"conscientiousness": -0.01}}},
        ]

        reflector = AtomicReflection()
        analysis = reflector.analyze(events)

        deltas = analysis["trait_deltas"]
        assert abs(deltas["O"] - 0.04) < 0.001  # (0.05 + 0.03) / 2
        assert abs(deltas["C"] - (-0.015)) < 0.001  # (-0.02 + -0.01) / 2
        assert abs(deltas["E"] - 0.01) < 0.001  # 0.01 / 1
        assert deltas["A"] == 0.0  # No updates
        assert deltas["N"] == 0.0  # No updates

    def test_novelty_indicators_calculation(self):
        """Should correctly calculate novelty and emergence indicators."""
        events = [
            {"kind": "reflection", "content": "analyzing current state"},
            {"kind": "reflection", "content": "reviewing past decisions"},
            {"kind": "reflection", "content": "current state needs attention"},
            {
                "kind": "emergence_report",
                "meta": {"metrics": {"composite_score": 0.75}},
            },
        ]

        reflector = AtomicReflection()
        analysis = reflector.analyze(events)

        indicators = analysis["novelty_indicators"]
        assert indicators["reflection_diversity"] > 0.0  # Should have diversity
        assert indicators["emergence_score"] == 0.75

    def test_window_size_limiting(self):
        """Should respect window size for event processing."""
        # Create more events than window size
        events = []
        for i in range(150):
            events.append({"kind": "test_event", "content": f"event {i}"})

        reflector = AtomicReflection(window_size=50)
        analysis = reflector.analyze(events)

        assert analysis["event_count"] == 50
        assert analysis["window_size"] == 50


class TestAtomicReflectionPropose:
    """Test AtomicReflection.propose() deterministic proposals."""

    def test_empty_analysis_returns_empty_proposals(self):
        """Empty analysis should return empty proposals."""
        analysis = {
            "commitment_stats": {
                "opens": 0,
                "closes": 0,
                "close_rate": 0.0,
                "streak": 0,
            },
            "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {"reflection_diversity": 0.0, "emergence_score": 0.0},
        }

        reflector = AtomicReflection()
        proposals = reflector.propose(analysis)

        # Should have structure but empty lists
        assert "commitment_actions" in proposals
        assert "cadence_adjustments" in proposals
        assert "trait_reinforcements" in proposals
        assert "policy_updates" in proposals
        assert len(proposals["commitment_actions"]) == 0
        assert len(proposals["cadence_adjustments"]) == 0
        assert len(proposals["trait_reinforcements"]) == 0

    def test_low_close_rate_proposes_reduction(self):
        """Low close rate should propose commitment load reduction."""
        analysis = {
            "commitment_stats": {
                "opens": 10,
                "closes": 2,
                "close_rate": 0.2,
                "streak": 0,
            },
            "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {"reflection_diversity": 0.5, "emergence_score": 0.5},
        }

        reflector = AtomicReflection()
        proposals = reflector.propose(analysis)

        actions = proposals["commitment_actions"]
        assert len(actions) == 1
        assert actions[0]["action"] == "reduce_commitment_load"
        assert actions[0]["priority"] == "high"
        assert "0.20" in actions[0]["reason"]

    def test_high_close_rate_proposes_increase(self):
        """High close rate should propose increased ambition."""
        analysis = {
            "commitment_stats": {
                "opens": 10,
                "closes": 9,
                "close_rate": 0.9,
                "streak": 3,
            },
            "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {"reflection_diversity": 0.5, "emergence_score": 0.5},
        }

        reflector = AtomicReflection()
        proposals = reflector.propose(analysis)

        actions = proposals["commitment_actions"]
        assert len(actions) == 1
        assert actions[0]["action"] == "increase_commitment_ambition"
        assert actions[0]["priority"] == "medium"
        assert "0.90" in actions[0]["reason"]

    def test_low_diversity_proposes_frequency_increase(self):
        """Low reflection diversity should propose increased frequency."""
        analysis = {
            "commitment_stats": {
                "opens": 5,
                "closes": 3,
                "close_rate": 0.6,
                "streak": 1,
            },
            "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {"reflection_diversity": 0.2, "emergence_score": 0.5},
            "events": [{"kind": "reflection", "content": "test reflection"}],
        }

        reflector = AtomicReflection()
        proposals = reflector.propose(analysis)

        adjustments = proposals["cadence_adjustments"]
        assert len(adjustments) == 1
        assert adjustments[0]["action"] == "increase_reflection_frequency"
        assert adjustments[0]["adjustment"]["min_turns"] == -1
        assert adjustments[0]["adjustment"]["min_time_s"] == -10

    def test_high_diversity_proposes_frequency_decrease(self):
        """High reflection diversity should propose decreased frequency."""
        analysis = {
            "commitment_stats": {
                "opens": 5,
                "closes": 3,
                "close_rate": 0.6,
                "streak": 1,
            },
            "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {"reflection_diversity": 0.8, "emergence_score": 0.5},
            "events": [{"kind": "reflection", "content": "test reflection"}],
        }

        reflector = AtomicReflection()
        proposals = reflector.propose(analysis)

        adjustments = proposals["cadence_adjustments"]
        assert len(adjustments) == 1
        assert adjustments[0]["action"] == "decrease_reflection_frequency"
        assert adjustments[0]["adjustment"]["min_turns"] == 1
        assert adjustments[0]["adjustment"]["min_time_s"] == 10

    def test_significant_trait_drift_proposes_reinforcement(self):
        """Significant trait drift should propose reinforcement."""
        analysis = {
            "commitment_stats": {
                "opens": 5,
                "closes": 3,
                "close_rate": 0.6,
                "streak": 1,
            },
            "trait_deltas": {"O": 0.15, "C": -0.12, "E": 0.05, "A": 0.0, "N": 0.0},
            "novelty_indicators": {"reflection_diversity": 0.5, "emergence_score": 0.5},
        }

        reflector = AtomicReflection()
        proposals = reflector.propose(analysis)

        reinforcements = proposals["trait_reinforcements"]
        assert len(reinforcements) == 2  # O and C exceed threshold

        # Check openness reinforcement
        o_reinforce = next(r for r in reinforcements if r["trait"] == "O")
        assert o_reinforce["action"] == "reinforce_increase"
        assert o_reinforce["delta"] == 0.15

        # Check conscientiousness reinforcement
        c_reinforce = next(r for r in reinforcements if r["trait"] == "C")
        assert c_reinforce["action"] == "reinforce_decrease"
        assert c_reinforce["delta"] == -0.12

    def test_low_emergence_proposes_threshold_decrease(self):
        """Low emergence score should propose threshold decrease."""
        analysis = {
            "commitment_stats": {
                "opens": 5,
                "closes": 3,
                "close_rate": 0.6,
                "streak": 1,
            },
            "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {
                "reflection_diversity": 0.5,
                "emergence_score": 0.15,
            },
        }

        reflector = AtomicReflection()
        proposals = reflector.propose(analysis)

        updates = proposals["policy_updates"]
        assert len(updates) == 1
        assert updates[0]["component"] == "novelty_threshold"
        assert updates[0]["action"] == "decrease_threshold"
        assert updates[0]["value"] == 0.05

    def test_high_emergence_proposes_threshold_increase(self):
        """High emergence score should propose threshold increase."""
        analysis = {
            "commitment_stats": {
                "opens": 5,
                "closes": 3,
                "close_rate": 0.6,
                "streak": 1,
            },
            "trait_deltas": {"O": 0.0, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {
                "reflection_diversity": 0.5,
                "emergence_score": 0.85,
            },
        }

        reflector = AtomicReflection()
        proposals = reflector.propose(analysis)

        updates = proposals["policy_updates"]
        assert len(updates) == 1
        assert updates[0]["component"] == "novelty_threshold"
        assert updates[0]["action"] == "increase_threshold"
        assert updates[0]["value"] == 0.05

    def test_deterministic_proposals_same_analysis(self):
        """Same analysis should produce identical proposals."""
        analysis = {
            "commitment_stats": {
                "opens": 8,
                "closes": 2,
                "close_rate": 0.25,
                "streak": 1,
            },
            "trait_deltas": {"O": 0.12, "C": 0.0, "E": 0.0, "A": 0.0, "N": 0.0},
            "novelty_indicators": {
                "reflection_diversity": 0.25,
                "emergence_score": 0.18,
            },
        }

        reflector = AtomicReflection()
        proposals1 = reflector.propose(analysis)
        proposals2 = reflector.propose(analysis)

        assert proposals1 == proposals2


class TestAtomicReflectionCommit:
    """Test AtomicReflection.commit() idempotent event emissions."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.eventlog = EventLog(self.temp_db.name)
        self.reflector = AtomicReflection()

    def tearDown(self):
        try:
            import os

            os.unlink(self.temp_db.name)
        except OSError:
            pass

    def test_commit_appends_three_steps(self):
        """commit() should append exactly three atomic_reflection_step events."""
        self.setUp()
        try:
            proposals = {
                "commitment_actions": [{"action": "test"}],
                "cadence_adjustments": [],
                "trait_reinforcements": [],
                "policy_updates": [],
            }

            appended_ids = self.reflector.commit(self.eventlog, proposals, "src_123")

            # Should append 3 events (analyze, propose, commit)
            assert len(appended_ids) == 3

            # Verify events in ledger
            events = self.eventlog.read_all()
            reflection_steps = [
                e for e in events if e.get("kind") == "atomic_reflection_step"
            ]
            assert len(reflection_steps) == 3

            # Check step contents
            steps = [e.get("content") for e in reflection_steps]
            assert "analyze" in steps
            assert "propose" in steps
            assert "commit" in steps
        finally:
            self.tearDown()

    def test_commit_idempotency_same_src_event_id(self):
        """Re-running commit with same src_event_id should emit nothing."""
        self.setUp()
        try:
            proposals = {
                "commitment_actions": [{"action": "test"}],
                "cadence_adjustments": [],
                "trait_reinforcements": [],
                "policy_updates": [],
            }

            # First commit
            appended_ids1 = self.reflector.commit(self.eventlog, proposals, "src_123")
            assert len(appended_ids1) == 3

            # Second commit with same src_event_id
            appended_ids2 = self.reflector.commit(self.eventlog, proposals, "src_123")
            assert len(appended_ids2) == 0  # Nothing appended

            # Verify total events unchanged
            events = self.eventlog.read_all()
            reflection_steps = [
                e for e in events if e.get("kind") == "atomic_reflection_step"
            ]
            assert len(reflection_steps) == 3
        finally:
            self.tearDown()

    def test_commit_different_src_event_ids(self):
        """Different src_event_ids should allow separate commits."""
        self.setUp()
        try:
            proposals = {
                "commitment_actions": [{"action": "test"}],
                "cadence_adjustments": [],
                "trait_reinforcements": [],
                "policy_updates": [],
            }

            # First commit
            appended_ids1 = self.reflector.commit(self.eventlog, proposals, "src_123")
            assert len(appended_ids1) == 3

            # Second commit with different src_event_id
            appended_ids2 = self.reflector.commit(self.eventlog, proposals, "src_456")
            assert len(appended_ids2) == 3

            # Verify total events
            events = self.eventlog.read_all()
            reflection_steps = [
                e for e in events if e.get("kind") == "atomic_reflection_step"
            ]
            assert len(reflection_steps) == 6  # 3 + 3
        finally:
            self.tearDown()

    def test_commit_metadata_integrity(self):
        """Events should contain proper metadata with deterministic digest."""
        self.setUp()
        try:
            proposals = {
                "commitment_actions": [{"action": "test_action"}],
                "cadence_adjustments": [{"adjustment": "test_adj"}],
                "trait_reinforcements": [],
                "policy_updates": [],
            }

            self.reflector.commit(self.eventlog, proposals, "src_789")

            events = self.eventlog.read_all()
            reflection_steps = [
                e for e in events if e.get("kind") == "atomic_reflection_step"
            ]

            for event in reflection_steps:
                meta = event.get("meta", {})
                assert meta.get("component") == "atomic_reflection"
                assert meta.get("src_event_id") == "src_789"
                assert meta.get("deterministic") is True
                assert meta.get("step") in ["analyze", "propose", "commit"]

                # Propose step should have digest
                if event.get("content") == "propose":
                    assert "digest" in meta
                    assert "proposals" in meta
                    assert meta["proposals"] == proposals
        finally:
            self.tearDown()


class TestAtomicReflectionReplayability:
    """Test complete replayability of atomic reflection system."""

    def test_full_cycle_replayability(self):
        """Run analyze → propose → commit twice; verify identical results."""
        temp_db1 = tempfile.NamedTemporaryFile(delete=False)
        temp_db2 = tempfile.NamedTemporaryFile(delete=False)

        try:
            eventlog1 = EventLog(temp_db1.name)
            eventlog2 = EventLog(temp_db2.name)

            events = [
                {"kind": "commitment_open", "content": "test commitment 1"},
                {"kind": "commitment_open", "content": "test commitment 2"},
                {"kind": "commitment_close", "content": "test commitment 1"},
                {"kind": "trait_update", "meta": {"changes": {"openness": 0.12}}},
                {"kind": "reflection", "content": "analyzing current system state"},
                {
                    "kind": "emergence_report",
                    "meta": {"metrics": {"composite_score": 0.25}},
                },
            ]

            reflector1 = AtomicReflection()
            reflector2 = AtomicReflection()

            # Run full cycle on both
            result1 = reflector1.run_full_cycle(eventlog1, events, "src_replay_test")
            result2 = reflector2.run_full_cycle(eventlog2, events, "src_replay_test")

            # Analysis should be identical
            assert result1["analysis"] == result2["analysis"]

            # Proposals should be identical
            assert result1["proposals"] == result2["proposals"]

            # Both should have committed 3 events
            assert len(result1["committed_event_ids"]) == 3
            assert len(result2["committed_event_ids"]) == 3

            # Verify ledger events are byte-equal
            events1 = eventlog1.read_all()
            events2 = eventlog2.read_all()

            steps1 = [e for e in events1 if e.get("kind") == "atomic_reflection_step"]
            steps2 = [e for e in events2 if e.get("kind") == "atomic_reflection_step"]

            assert len(steps1) == len(steps2) == 3

            # Compare metadata (excluding event IDs which may differ)
            for step1, step2 in zip(steps1, steps2):
                assert step1.get("content") == step2.get("content")
                meta1 = step1.get("meta", {})
                meta2 = step2.get("meta", {})

                # Compare all metadata except potentially auto-generated fields
                for key in ["component", "step", "src_event_id", "deterministic"]:
                    assert meta1.get(key) == meta2.get(key)

                # For propose step, compare digest and proposals
                if step1.get("content") == "propose":
                    assert meta1.get("digest") == meta2.get("digest")
                    assert meta1.get("proposals") == meta2.get("proposals")

        finally:
            import os

            try:
                os.unlink(temp_db1.name)
                os.unlink(temp_db2.name)
            except OSError:
                pass

    def test_deterministic_behavior_across_instances(self):
        """Different AtomicReflection instances should produce identical results."""
        events = [
            {"kind": "commitment_open", "content": "commit 1"},
            {"kind": "commitment_close", "content": "commit 1"},
            {"kind": "trait_update", "meta": {"changes": {"conscientiousness": -0.15}}},
            {"kind": "reflection", "content": "reviewing system performance metrics"},
            {
                "kind": "emergence_report",
                "meta": {"metrics": {"composite_score": 0.82}},
            },
        ]

        reflector1 = AtomicReflection(window_size=50)
        reflector2 = AtomicReflection(window_size=50)

        # Analyze
        analysis1 = reflector1.analyze(events)
        analysis2 = reflector2.analyze(events)
        assert analysis1 == analysis2

        # Propose
        proposals1 = reflector1.propose(analysis1)
        proposals2 = reflector2.propose(analysis2)
        assert proposals1 == proposals2


class TestAtomicReflectionIntegration:
    """Integration tests for complete atomic reflection workflow."""

    def test_realistic_workflow(self):
        """Test complete workflow with realistic event sequence."""
        temp_db = tempfile.NamedTemporaryFile(delete=False)

        try:
            eventlog = EventLog(temp_db.name)

            # Create realistic event sequence
            events = [
                {
                    "kind": "identity_adopt",
                    "content": "Echo",
                    "meta": {"confidence": 0.9},
                },
                {"kind": "commitment_open", "content": "analyze system performance"},
                {"kind": "commitment_open", "content": "review reflection patterns"},
                {"kind": "commitment_open", "content": "optimize trait stability"},
                {
                    "kind": "reflection",
                    "content": "current system shows good autonomy metrics",
                },
                {"kind": "commitment_close", "content": "analyze system performance"},
                {
                    "kind": "trait_update",
                    "meta": {"changes": {"openness": 0.03, "conscientiousness": -0.01}},
                },
                {
                    "kind": "reflection",
                    "content": "performance analysis reveals optimization opportunities",
                },
                {
                    "kind": "emergence_report",
                    "meta": {"metrics": {"composite_score": 0.45}},
                },
                {"kind": "commitment_close", "content": "review reflection patterns"},
            ]

            reflector = AtomicReflection()
            result = reflector.run_full_cycle(eventlog, events, "integration_test_001")

            # Verify analysis structure
            analysis = result["analysis"]
            assert "commitment_stats" in analysis
            assert "trait_deltas" in analysis
            assert "novelty_indicators" in analysis

            # Verify proposals generated
            proposals = result["proposals"]
            assert "commitment_actions" in proposals
            assert "cadence_adjustments" in proposals
            assert "trait_reinforcements" in proposals
            assert "policy_updates" in proposals

            # Verify events committed
            assert len(result["committed_event_ids"]) == 3

            # Verify ledger integrity
            all_events = eventlog.read_all()
            reflection_steps = [
                e for e in all_events if e.get("kind") == "atomic_reflection_step"
            ]
            assert len(reflection_steps) == 3

            # Verify step sequence
            step_contents = [e.get("content") for e in reflection_steps]
            assert step_contents == ["analyze", "propose", "commit"]

        finally:
            import os

            try:
                os.unlink(temp_db.name)
            except OSError:
                pass
