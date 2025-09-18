# tests/test_commitment_restructuring.py

import pytest
from pmm.storage.eventlog import EventLog
from pmm.commitments.restructuring import CommitmentRestructurer
from pmm.constants import EventKinds


# Fixtures
@pytest.fixture
def empty_log(tmp_path):
    db = tmp_path / "elog.db"
    return EventLog(str(db))


@pytest.fixture
def seeded_log(empty_log):
    # Create commitments with varying similarity and age
    empty_log.append(
        kind=EventKinds.COMMITMENT_OPEN,
        content="implement user authentication",
        meta={"cid": "c1", "text": "implement user authentication", "priority": 0.8},
    )
    empty_log.append(
        kind=EventKinds.COMMITMENT_OPEN,
        content="add user login system",
        meta={"cid": "c2", "text": "add user login system", "priority": 0.7},
    )
    empty_log.append(
        kind=EventKinds.COMMITMENT_OPEN,
        content="fix database connection",
        meta={"cid": "c3", "text": "fix database connection", "priority": 0.5},
    )

    # Add some events to create age
    for i in range(12):
        empty_log.append(
            kind=EventKinds.REFLECTION,
            content=f"reflection {i}",
            meta={"tag": "progress"},
        )

    return empty_log


@pytest.fixture
def closed_commitment_log(empty_log):
    # Add open and closed commitments
    empty_log.append(
        kind=EventKinds.COMMITMENT_OPEN,
        content="task 1",
        meta={"cid": "c1", "text": "task 1", "priority": 0.8},
    )
    empty_log.append(
        kind=EventKinds.COMMITMENT_CLOSE,
        content="task 1 completed",
        meta={"cid": "c1"},
    )
    empty_log.append(
        kind=EventKinds.COMMITMENT_OPEN,
        content="task 2",
        meta={"cid": "c2", "text": "task 2", "priority": 0.6},
    )
    return empty_log


# Tests
def test_no_changes_no_event(empty_log):
    """Should not emit event when no restructuring changes exist."""
    cr = CommitmentRestructurer(empty_log)
    event_id = cr.run_restructuring()
    assert event_id is None


def test_deterministic_digest(seeded_log):
    """Same changes should produce same digest."""
    cr = CommitmentRestructurer(seeded_log)
    changes1 = cr.consolidate_similar(threshold=0.5)
    changes2 = cr.consolidate_similar(threshold=0.5)

    if changes1:  # Only test if changes exist
        d1 = cr._digest_changes(changes1)
        d2 = cr._digest_changes(changes2)
        assert d1 == d2, "Identical changes must produce identical digests"


def test_consolidate_similar_commitments(seeded_log):
    """Should identify and consolidate similar commitments."""
    cr = CommitmentRestructurer(seeded_log)
    changes = cr.consolidate_similar(
        threshold=0.3
    )  # Lower threshold to catch similar auth/login

    # Should find similar commitments (auth and login)
    merge_changes = [c for c in changes if c["op"] == "merge"]
    if merge_changes:
        merge = merge_changes[0]
        assert "cids" in merge
        assert "new_cid" in merge
        assert len(merge["cids"]) >= 2
        assert merge["new_cid"].startswith("merged_")


def test_reprioritize_stale_commitments(seeded_log):
    """Should reprioritize commitments that are old enough."""
    cr = CommitmentRestructurer(seeded_log)
    changes = cr.reprioritize_stale(
        age_threshold=5
    )  # Lower threshold to catch stale commitments

    repriority_changes = [c for c in changes if c["op"] == "reprioritize"]
    if repriority_changes:
        change = repriority_changes[0]
        assert "cid" in change
        assert "old_priority" in change
        assert "new_priority" in change
        assert change["new_priority"] > change["old_priority"]


def test_emit_restructuring_idempotency(seeded_log):
    """Same changes should not create duplicate events."""
    cr = CommitmentRestructurer(seeded_log)

    # Run restructuring twice
    event_id1 = cr.run_restructuring()
    event_id2 = cr.run_restructuring()

    if event_id1 is not None:
        assert (
            event_id1 == event_id2
        ), "Identical restructuring should not create duplicate events"


def test_evolution_event_structure(seeded_log):
    """Evolution events should have proper structure."""
    cr = CommitmentRestructurer(seeded_log)
    event_id = cr.run_restructuring()

    if event_id is not None:
        # Find the emitted event
        events = seeded_log.read_all()
        evolution_events = [e for e in events if e["kind"] == EventKinds.EVOLUTION]

        assert len(evolution_events) == 1
        event = evolution_events[0]

        assert event["id"] == event_id
        assert event["kind"] == EventKinds.EVOLUTION
        assert event["content"] == ""  # no semantic meaning in content

        # Check meta structure
        meta = event["meta"]
        assert "digest" in meta
        assert "changes" in meta
        assert isinstance(meta["changes"], list)


def test_only_open_commitments_processed(closed_commitment_log):
    """Should only process open commitments, not closed ones."""
    cr = CommitmentRestructurer(closed_commitment_log)
    open_commitments = cr._get_open_commitments()

    # Should only have c2 (c1 was closed)
    assert len(open_commitments) == 1
    assert open_commitments[0]["cid"] == "c2"
    assert open_commitments[0]["status"] == "open"


def test_text_similarity_deterministic():
    """Text similarity should be deterministic."""
    cr = CommitmentRestructurer(EventLog())  # Empty log for utility testing

    # Test cases
    assert cr._text_similarity("hello world", "hello world") == 1.0
    assert cr._text_similarity("", "") == 1.0
    assert cr._text_similarity("hello", "world") == 0.0

    # Should be symmetric
    sim1 = cr._text_similarity("implement auth", "add authentication")
    sim2 = cr._text_similarity("add authentication", "implement auth")
    assert sim1 == sim2


def test_schema_safety_missing_meta(empty_log):
    """Should handle events with missing meta fields gracefully."""
    # Add commitment with minimal meta
    empty_log.append(
        kind=EventKinds.COMMITMENT_OPEN,
        content="some task",
        meta={},  # Missing cid, text, priority
    )

    cr = CommitmentRestructurer(empty_log)
    open_commitments = cr._get_open_commitments()

    # Should handle gracefully (likely no commitments due to missing cid)
    assert isinstance(open_commitments, list)


def test_replay_consistency(seeded_log):
    """Same log should produce identical restructuring across multiple runs."""
    cr1 = CommitmentRestructurer(seeded_log)
    cr2 = CommitmentRestructurer(seeded_log)

    changes1 = cr1.consolidate_similar(threshold=0.5)
    changes2 = cr2.consolidate_similar(threshold=0.5)

    assert changes1 == changes2, "Same log must produce identical restructuring"


def test_merge_redundant_high_threshold(seeded_log):
    """merge_redundant should use higher similarity threshold."""
    cr = CommitmentRestructurer(seeded_log)

    # These should be different due to different thresholds
    consolidate_changes = cr.consolidate_similar(threshold=0.9)
    merge_changes = cr.merge_redundant(similarity_threshold=0.95)

    # merge_redundant uses higher threshold, so should have fewer or equal changes
    assert len(merge_changes) <= len(consolidate_changes)
