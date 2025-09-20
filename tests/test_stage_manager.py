import pytest
from pmm.runtime.stage_manager import StageManager
from pmm.storage.eventlog import EventLog
from pmm.constants import EventKinds
from helpers.stage_seeding import (
    _seed_reflections,
    _seed_restructures,
    _seed_metrics,
    seed_stage_progression,
)


@pytest.fixture
def eventlog(tmp_path):
    return EventLog(str(tmp_path / "test_stage.db"))


def test_s0_to_s1_advancement_deterministic(eventlog):
    """Test deterministic S0→S1 advancement with exact criteria."""
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)  # Above hysteresis threshold

    sm = StageManager(eventlog)
    stage_before = sm.current_stage()
    event_id = sm.check_and_advance()

    assert stage_before == "S0"
    assert sm.current_stage() == "S1"
    ev = eventlog.get_event(int(event_id))
    assert ev["kind"] == EventKinds.STAGE_UPDATE
    assert ev["meta"]["from"] == "S0"
    assert ev["meta"]["to"] == "S1"


def test_s1_to_s2_advancement_deterministic(eventlog):
    """Test deterministic S1→S2 advancement with exact criteria."""
    # First advance to S1
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)

    sm = StageManager(eventlog)
    sm.check_and_advance()  # S0→S1

    # Then meet S2 criteria
    _seed_reflections(eventlog, 5)
    _seed_restructures(eventlog, 4)
    _seed_metrics(eventlog, 0.74, 0.39)  # Above hysteresis threshold

    event_id = sm.check_and_advance()

    assert sm.current_stage() == "S2"
    ev = eventlog.get_event(int(event_id))
    assert ev["kind"] == EventKinds.STAGE_UPDATE
    assert ev["meta"]["from"] == "S1"
    assert ev["meta"]["to"] == "S2"


def test_no_advancement_if_criteria_not_met(eventlog):
    """Test no advancement when criteria are not met."""
    _seed_reflections(eventlog, 1)  # below threshold (need 2)
    _seed_restructures(eventlog, 0)  # below threshold (need 1)
    _seed_metrics(eventlog, 0.40, 0.10)  # below all thresholds

    sm = StageManager(eventlog)
    stage_before = sm.current_stage()
    event_id = sm.check_and_advance()

    assert stage_before == "S0"
    assert sm.current_stage() == "S0"
    assert event_id is None


def test_hysteresis_buffer_prevents_thrash(eventlog):
    """Test hysteresis buffer prevents stage thrashing."""
    _seed_reflections(eventlog, 2)
    _seed_restructures(eventlog, 1)
    _seed_metrics(
        eventlog, 0.51, 0.16
    )  # within hysteresis band (0.50+0.03=0.53, 0.15+0.03=0.18)

    sm = StageManager(eventlog)
    stage_before = sm.current_stage()
    event_id = sm.check_and_advance()

    assert sm.current_stage() == stage_before
    assert event_id is None


def test_stage_advancement_idempotent(eventlog):
    """Test stage advancement is idempotent with digest-based deduplication."""
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)

    sm = StageManager(eventlog)

    # First advancement should succeed
    first_id = sm.check_and_advance()
    assert first_id is not None
    assert sm.current_stage() == "S1"

    # Second call should return None since already advanced
    second_id = sm.check_and_advance()
    assert second_id is None

    # Verify idempotency by checking digest uniqueness
    stage_events = [
        e for e in eventlog.read_all() if e["kind"] == EventKinds.STAGE_UPDATE
    ]
    s0_to_s1_events = [
        e for e in stage_events if e["meta"]["from"] == "S0" and e["meta"]["to"] == "S1"
    ]
    assert len(s0_to_s1_events) == 1  # only one S0->S1 transition


def test_replay_consistency(tmp_path):
    """Test replay consistency across identical databases."""
    db1 = tmp_path / "stage1.db"
    db2 = tmp_path / "stage2.db"

    seed_stage_progression(db1, upto="S2")
    seed_stage_progression(db2, upto="S2")

    sm1 = StageManager(EventLog(str(db1)))
    sm2 = StageManager(EventLog(str(db2)))

    assert sm1.current_stage() == sm2.current_stage()
    assert sm1.snapshot_digest() == sm2.snapshot_digest()


def test_identity_lock_on_stage_transition(eventlog):
    """Test identity lock event is emitted on stage transition."""
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)

    sm = StageManager(eventlog)
    sm.check_and_advance()

    locks = [e for e in eventlog.read_all() if e["kind"] == EventKinds.IDENTITY_LOCK]
    assert len(locks) == 1
    assert locks[0]["meta"]["stage"] == "S1"


def test_policy_update_emitted_on_stage_advancement(eventlog):
    """Test policy update event is emitted on stage advancement."""
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)

    sm = StageManager(eventlog)
    sm.check_and_advance()

    updates = [e for e in eventlog.read_all() if e["kind"] == EventKinds.POLICY_UPDATE]
    assert len(updates) >= 1
    assert any("reflection_cadence" in u["meta"] for u in updates)


def test_current_stage_defaults_to_s0(eventlog):
    """Test current_stage defaults to S0 when no stage events exist."""
    sm = StageManager(eventlog)
    assert sm.current_stage() == "S0"


def test_stage_progression_sequence(eventlog):
    """Test complete stage progression sequence S0→S1→S2→S3→S4."""
    sm = StageManager(eventlog)

    # S0→S1
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)
    sm.check_and_advance()
    assert sm.current_stage() == "S1"

    # S1→S2
    _seed_reflections(eventlog, 5)
    _seed_restructures(eventlog, 4)
    _seed_metrics(eventlog, 0.74, 0.39)
    sm.check_and_advance()
    assert sm.current_stage() == "S2"

    # S2→S3
    _seed_reflections(eventlog, 8)
    _seed_restructures(eventlog, 6)
    _seed_metrics(eventlog, 0.84, 0.54)
    sm.check_and_advance()
    assert sm.current_stage() == "S3"

    # S3→S4
    _seed_reflections(eventlog, 12)
    _seed_restructures(eventlog, 8)
    _seed_metrics(eventlog, 0.89, 0.79)
    sm.check_and_advance()
    assert sm.current_stage() == "S4"


def test_no_advancement_beyond_s4(eventlog):
    """Test no advancement beyond S4 (terminal stage)."""
    # Manually seed all stages to S4
    _seed_reflections(eventlog, 12)
    _seed_restructures(eventlog, 8)
    _seed_metrics(eventlog, 0.89, 0.79)

    sm = StageManager(eventlog)
    # Advance through all stages
    sm.check_and_advance()  # S0->S1
    sm.check_and_advance()  # S1->S2
    sm.check_and_advance()  # S2->S3
    sm.check_and_advance()  # S3->S4

    assert sm.current_stage() == "S4"

    # Try to advance beyond S4
    event_id = sm.check_and_advance()
    assert event_id is None
    assert sm.current_stage() == "S4"


def test_snapshot_digest_deterministic(eventlog):
    """Test snapshot digest is deterministic for same stage."""
    sm1 = StageManager(eventlog)
    sm2 = StageManager(eventlog)

    assert sm1.snapshot_digest() == sm2.snapshot_digest()

    # After advancement, digests should still match
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)

    sm1.check_and_advance()
    sm2 = StageManager(eventlog)  # Fresh instance

    assert sm1.snapshot_digest() == sm2.snapshot_digest()


def test_cadence_policy_by_stage(eventlog):
    """Test reflection cadence policy varies by stage."""
    sm = StageManager(eventlog)

    # S0→S1 should emit liberalized cadence
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)
    sm.check_and_advance()

    updates = [e for e in eventlog.read_all() if e["kind"] == EventKinds.POLICY_UPDATE]
    s1_update = [u for u in updates if u["meta"].get("stage") == "S1"][0]
    assert s1_update["meta"]["reflection_cadence"] == "liberalized"

    # S2→S3 should emit standard cadence - need to meet S2 and S3 criteria
    _seed_reflections(eventlog, 8)
    _seed_restructures(eventlog, 6)
    _seed_metrics(eventlog, 0.84, 0.54)
    sm.check_and_advance()  # S1→S2

    _seed_reflections(eventlog, 12)
    _seed_restructures(eventlog, 8)
    _seed_metrics(eventlog, 0.89, 0.79)
    sm.check_and_advance()  # S2→S3

    updates = [e for e in eventlog.read_all() if e["kind"] == EventKinds.POLICY_UPDATE]
    s3_update = [u for u in updates if u["meta"].get("stage") == "S3"][0]
    assert s3_update["meta"]["reflection_cadence"] == "standard"
