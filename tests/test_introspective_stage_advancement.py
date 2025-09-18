# tests/test_introspective_stage_advancement.py

from pmm.storage.eventlog import EventLog
from pmm.runtime.stage_manager import StageManager
from pmm.constants import EventKinds


def test_introspective_emergence_triggers_s0_s1_advancement():
    """Test that introspective behaviors trigger S0→S1 advancement even with lower IAS/GAS."""
    eventlog = EventLog(":memory:")
    stage_manager = StageManager(eventlog)

    # Start at S0
    assert stage_manager.current_stage() == "S0"

    # Add basic metrics (lower than traditional thresholds)
    eventlog.append(
        kind=EventKinds.METRICS_UPDATE,
        content="",
        meta={"ias": 0.45, "gas": 0.10},  # Below traditional S0→S1 thresholds
    )

    # Add reflections (meets basic requirement)
    for i in range(3):
        eventlog.append(
            kind=EventKinds.REFLECTION,
            content=f"Reflection {i+1} on my growth patterns",
            meta={"rid": f"r{i+1}", "insight": f"insight_{i+1}"},
        )

    # Add introspection queries (evidence of self-inspection)
    eventlog.append(
        kind=EventKinds.INTROSPECTION_QUERY,
        content="",
        meta={"query_type": "commitment_analysis", "patterns_found": 5},
    )
    eventlog.append(
        kind=EventKinds.INTROSPECTION_QUERY,
        content="",
        meta={"query_type": "reflection_analysis", "themes_identified": 3},
    )

    # Add identity adoptions (evidence of identity evolution)
    eventlog.append(
        kind=EventKinds.IDENTITY_ADOPTION,
        content="",
        meta={"name": "Echo", "reason": "user_assignment"},
    )
    eventlog.append(
        kind=EventKinds.IDENTITY_ADOPTION,
        content="",
        meta={"name": "Persistent", "reason": "self_definition"},
    )

    # Should advance via introspective emergence path
    # IAS 0.45 ≥ 0.43 (0.40 + 0.03 hysteresis) AND all other criteria met
    result = stage_manager.check_and_advance()
    assert result is not None
    assert stage_manager.current_stage() == "S1"


def test_traditional_criteria_still_work():
    """Test that traditional high-metric advancement still works."""
    eventlog = EventLog(":memory:")
    stage_manager = StageManager(eventlog)

    # Add high metrics (traditional path)
    eventlog.append(
        kind=EventKinds.METRICS_UPDATE,
        content="",
        meta={"ias": 0.65, "gas": 0.25},  # Above traditional thresholds
    )

    # Add required reflections and evolution events
    for i in range(3):
        eventlog.append(
            kind=EventKinds.REFLECTION,
            content=f"Traditional reflection {i+1}",
            meta={"rid": f"tr{i+1}"},
        )

    for i in range(2):
        eventlog.append(
            kind=EventKinds.EVOLUTION,
            content="",
            meta={"changes": {"trait_drift": f"change_{i+1}"}},
        )

    # Should advance via traditional criteria
    result = stage_manager.check_and_advance()
    assert result is not None
    assert stage_manager.current_stage() == "S1"


def test_insufficient_introspective_evidence_blocks_advancement():
    """Test that insufficient introspective evidence prevents advancement."""
    eventlog = EventLog(":memory:")
    stage_manager = StageManager(eventlog)

    # Add metrics at introspective threshold
    eventlog.append(
        kind=EventKinds.METRICS_UPDATE,
        content="",
        meta={"ias": 0.47, "gas": 0.08},  # Above introspective threshold
    )

    # Add reflections
    for i in range(3):
        eventlog.append(
            kind=EventKinds.REFLECTION,
            content=f"Reflection {i+1}",
            meta={"rid": f"r{i+1}"},
        )

    # Add only ONE introspection query (need 2)
    eventlog.append(
        kind=EventKinds.INTROSPECTION_QUERY,
        content="",
        meta={"query_type": "single_query"},
    )

    # Add identity adoptions
    for i in range(2):
        eventlog.append(
            kind=EventKinds.IDENTITY_ADOPTION, content="", meta={"name": f"Name{i+1}"}
        )

    # Should NOT advance (insufficient introspection queries)
    result = stage_manager.check_and_advance()
    assert result is None
    assert stage_manager.current_stage() == "S0"


def test_introspective_emergence_idempotency():
    """Test that introspective emergence advancement is idempotent when called multiple times before stage change."""
    eventlog = EventLog(":memory:")
    stage_manager = StageManager(eventlog)

    # Set up introspective emergence conditions
    eventlog.append(
        kind=EventKinds.METRICS_UPDATE,
        content="",
        meta={"ias": 0.47, "gas": 0.08},  # Above introspective threshold
    )

    for i in range(3):
        eventlog.append(
            kind=EventKinds.REFLECTION, content=f"Reflection {i+1}", meta={}
        )

    for i in range(2):
        eventlog.append(kind=EventKinds.INTROSPECTION_QUERY, content="", meta={})
        eventlog.append(kind=EventKinds.IDENTITY_ADOPTION, content="", meta={})

    # First advancement S0→S1
    result1 = stage_manager.check_and_advance()
    assert result1 is not None
    assert stage_manager.current_stage() == "S1"

    # Second call should return None (now checking S1→S2 criteria, which aren't met)
    result2 = stage_manager.check_and_advance()
    assert result2 is None

    # Should still be at S1
    assert stage_manager.current_stage() == "S1"
