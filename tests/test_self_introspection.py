# tests/test_self_introspection.py

import pytest
from pmm.storage.eventlog import EventLog
from pmm.runtime.self_introspection import SelfIntrospection, _digest_events


# Fixtures
@pytest.fixture
def empty_log(tmp_path):
    db = tmp_path / "elog.db"
    return EventLog(str(db))


@pytest.fixture
def seeded_log(empty_log):
    # Minimal, schema-safe events
    empty_log.append(
        kind="commitment_open",
        content="do something",
        meta={"cid": "c1", "status": "open", "text": "do something"},
    )
    empty_log.append(
        kind="reflection",
        content="noticed clarity",
        meta={"rid": "r1", "topic": "focus"},
    )
    empty_log.append(
        kind="trait_update",
        content="0.75",
        meta={"trait": "openness", "reason": "reflection"},
    )
    empty_log.append(
        kind="commitment_close",
        content="completed task",
        meta={"cid": "c1", "status": "closed"},
    )
    return empty_log


# Tests
def test_digest_determinism(seeded_log):
    events = seeded_log.read_all()
    d1 = _digest_events(events)
    d2 = _digest_events(events)
    assert d1 == d2, "Digest must be stable across identical input"


def test_commitment_query_schema(seeded_log):
    si = SelfIntrospection(seeded_log)
    res = si.query_commitments(window=10)
    assert "commitments" in res
    assert "digest" in res
    for digest, data in res["commitments"].items():
        assert "cid" in data
        assert "text" in data
        assert "status" in data
        assert "kind" in data
        assert "id" in data


def test_reflection_query_schema(seeded_log):
    si = SelfIntrospection(seeded_log)
    res = si.analyze_reflections(window=10)
    assert "reflections" in res
    assert "digest" in res
    for r in res["reflections"]:
        assert "rid" in r
        assert "insight" in r
        assert "topic" in r
        assert "id" in r


def test_trait_query_schema(seeded_log):
    si = SelfIntrospection(seeded_log)
    res = si.track_traits(window=10)
    assert "traits" in res
    assert "digest" in res
    assert "openness" in res["traits"]
    for trait_name, trait_list in res["traits"].items():
        for trait_entry in trait_list:
            assert "value" in trait_entry
            assert "reason" in trait_entry
            assert "id" in trait_entry


def test_emit_query_event_idempotent(seeded_log):
    si = SelfIntrospection(seeded_log)
    payload = si.query_commitments(window=10)
    e1 = si.emit_query_event("commitments", payload)
    e2 = si.emit_query_event("commitments", payload)
    # Both events carry the same digest → same meta
    assert e1["meta"]["digest"] == e2["meta"]["digest"]


def test_replay_consistency(tmp_path, seeded_log):
    # Test that the same events produce the same digest
    si1 = SelfIntrospection(seeded_log)
    si2 = SelfIntrospection(seeded_log)

    # Query the same data twice - should produce identical results
    r1 = si1.query_commitments(window=10)
    r2 = si2.query_commitments(window=10)
    assert r1["digest"] == r2["digest"], "Same events must yield identical digest"

    # Also test that the actual commitment data is identical
    assert (
        r1["commitments"] == r2["commitments"]
    ), "Same events must yield identical commitment data"


def test_empty_log_handling(empty_log):
    si = SelfIntrospection(empty_log)

    # Should handle empty logs gracefully
    commitments = si.query_commitments(window=10)
    assert commitments["commitments"] == {}
    assert isinstance(commitments["digest"], str)

    reflections = si.analyze_reflections(window=10)
    assert reflections["reflections"] == []
    assert isinstance(reflections["digest"], str)

    traits = si.track_traits(window=10)
    assert traits["traits"] == {}
    assert isinstance(traits["digest"], str)


def test_missing_meta_fields(empty_log):
    # Test with events that have missing meta fields
    empty_log.append(
        kind="commitment_open",
        content="test commitment",
        meta={},  # Missing cid, status, text
    )
    empty_log.append(
        kind="reflection",
        content="test reflection",
        meta={},  # Missing rid, topic
    )
    empty_log.append(
        kind="trait_update",
        content="0.5",
        meta={},  # Missing trait, reason
    )

    si = SelfIntrospection(empty_log)

    # Should handle missing fields gracefully
    commitments = si.query_commitments(window=10)
    assert len(commitments["commitments"]) == 1

    reflections = si.analyze_reflections(window=10)
    assert len(reflections["reflections"]) == 1

    traits = si.track_traits(window=10)
    assert len(traits["traits"]) == 0  # No trait name, so not included
