from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.core.ledger_mirror import LedgerMirror, RecursiveSelfModel


def test_rsm_rebuild_parity_after_100_events():
    log = EventLog(":memory:")
    live = LedgerMirror(log)

    for idx in range(100):
        if idx % 5 == 0:
            log.append(kind="user_message", content="Who are you?", meta={})
        elif idx % 5 == 1:
            log.append(
                kind="assistant_message",
                content="I value determinism.",
                meta={"topic": "identity"},
            )
        elif idx % 5 == 2:
            log.append(
                kind="assistant_message",
                content="CLAIM: failed on math reasoning.",
                meta={"topic": "math"},
            )
        elif idx % 5 == 3:
            log.append(
                kind="reflection",
                content="Maintaining determinism across identity queries.",
                meta={},
            )
        else:
            log.append(
                kind="assistant_message",
                content="unknown status persisted.",
                meta={"topic": "physics"},
            )

    live_snapshot = live.rsm_snapshot()
    rebuilt = LedgerMirror(log)
    rebuilt_snapshot = rebuilt.rsm_snapshot()

    assert live_snapshot == rebuilt_snapshot


def test_rsm_detects_identity_pattern():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    log.append(kind="user_message", content="who are you?", meta={})
    log.append(
        kind="reflection",
        content="The answer leans on determinism principles.",
        meta={},
    )

    snapshot = mirror.rsm_snapshot()
    assert snapshot["behavioral_tendencies"].get("identity_query") == 1
    assert snapshot["behavioral_tendencies"].get("determinism_emphasis", 0) >= 1
    assert (
        "identity_queries_trigger_determinism_ref"
        in snapshot["interaction_meta_patterns"]
    )


def test_rsm_counts_knowledge_gaps_deterministically():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    for _ in range(4):
        log.append(
            kind="assistant_message",
            content="CLAIM: failed to explain integrals.",
            meta={"topic": "math"},
        )
    for _ in range(3):
        log.append(
            kind="assistant_message",
            content="Result remains unknown for physics.",
            meta={"topic": "physics"},
        )

    snapshot = mirror.rsm_snapshot()
    assert snapshot["knowledge_gaps"] == ["math"]
    assert mirror.rsm_knowledge_gaps() == 0

    for _ in range(500):
        log.append(kind="user_message", content="filler event", meta={})

    assert mirror.rsm_snapshot()["knowledge_gaps"] == []


def test_gaps_count_only_unresolved_intents():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    # Add one unresolved intent (count == 1)
    log.append(
        kind="assistant_message",
        content="CLAIM: failed to explain quantum physics.",
        meta={"topic": "quantum"},
    )

    # Add another unresolved intent
    log.append(
        kind="assistant_message",
        content="unknown status for chemistry.",
        meta={"topic": "chemistry"},
    )

    # Add a resolved intent (count == 2)
    log.append(
        kind="assistant_message",
        content="CLAIM: failed on biology.",
        meta={"topic": "biology"},
    )
    log.append(
        kind="assistant_message",
        content="biology remains unknown.",
        meta={"topic": "biology"},
    )

    # Check that unresolved count is 2
    assert mirror.rsm_knowledge_gaps() == 2

    # Snapshot intents should have quantum:1, chemistry:1, biology:2
    snapshot = mirror.rsm_snapshot()
    assert snapshot["intents"]["quantum"] == 1
    assert snapshot["intents"]["chemistry"] == 1
    assert snapshot["intents"]["biology"] == 2


def test_rsm_sync_idempotent_on_replay():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    log.append(kind="user_message", content="Who are you?", meta={})
    log.append(
        kind="assistant_message",
        content="CLAIM: failed to respond about math.",
        meta={"topic": "math"},
    )
    log.append(
        kind="reflection",
        content="Reinforce determinism stance in replies.",
        meta={},
    )
    log.append(
        kind="assistant_message",
        content="Information remains unknown regarding physics.",
        meta={"topic": "physics"},
    )

    snapshot_before = mirror.rsm_snapshot()
    for event in log.read_all():
        mirror.sync(event)
    snapshot_after = mirror.rsm_snapshot()

    assert snapshot_before == snapshot_after


def test_diff_rsm_shows_growth_in_determinism_refs():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    log.append(kind="user_message", content="hello", meta={})
    event_a = log.read_all()[-1]["id"]
    log.append(
        kind="assistant_message",
        content="Determinism guides this update.",
        meta={},
    )
    event_b = log.read_all()[-1]["id"]

    diff = mirror.diff_rsm(event_a, event_b)
    assert diff["tendencies_delta"] == {"determinism_emphasis": 1}
    assert diff["gaps_added"] == []
    assert diff["gaps_resolved"] == []


def test_diff_rsm_detects_gap_resolution():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    for _ in range(4):
        log.append(
            kind="assistant_message",
            content="CLAIM: failed explaining memory details.",
            meta={"topic": "memory"},
        )
    gap_event_id = log.read_all()[-1]["id"]

    for i in range(500):
        log.append(kind="user_message", content=f"filler {i}", meta={})
    final_event_id = log.read_all()[-1]["id"]

    diff = mirror.diff_rsm(gap_event_id, final_event_id)
    assert diff["tendencies_delta"] == {}
    assert diff["gaps_added"] == []
    assert diff["gaps_resolved"] == ["memory"]


def test_rsm_counts_stability_and_adaptability_occurrences():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    payload = ("stability adapt " * 3).strip()

    # 10 reflections + 5 assistant messages, each contains 3 occurrences
    for _ in range(10):
        log.append(kind="reflection", content=payload, meta={})
    for _ in range(5):
        log.append(kind="assistant_message", content=payload, meta={})

    snap = mirror.rsm_snapshot()
    tendencies = snap["behavioral_tendencies"]
    assert tendencies.get("stability_emphasis") == 45
    assert tendencies.get("adaptability_emphasis") == 45

    # Rebuild parity: a fresh mirror should match live snapshot
    rebuilt = LedgerMirror(log)
    assert rebuilt.rsm_snapshot() == snap


def test_rsm_caps_stability_adaptability_at_50():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    payload = ("stability adapt " * 3).strip()

    # 20 reflections -> 20 * 3 = 60 occurrences per marker; capped to 50
    for _ in range(20):
        log.append(kind="reflection", content=payload, meta={})

    tendencies = mirror.rsm_snapshot()["behavioral_tendencies"]
    assert tendencies.get("stability_emphasis") == 50
    assert tendencies.get("adaptability_emphasis") == 50


def test_rsm_instantiation_capacity_counts_and_caps():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    # 15 assistant + 10 reflections, each containing both markers once -> 60 mentions
    payload = "instantiation entity"
    for _ in range(15):
        log.append(kind="assistant_message", content=payload, meta={})
    for _ in range(10):
        log.append(kind="reflection", content=payload, meta={})

    tendencies = mirror.rsm_snapshot()["behavioral_tendencies"]
    # Capped at 50
    assert tendencies.get("instantiation_capacity") == 50

    # Rebuild parity
    rebuilt = LedgerMirror(log)
    assert rebuilt.rsm_snapshot() == mirror.rsm_snapshot()


def test_rsm_instantiation_capacity_counts_without_cap():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    # 20 mentions total -> expected exact 20 (single marker per message)
    payload = "instantiation"
    for _ in range(10):
        log.append(kind="assistant_message", content=payload, meta={})
    for _ in range(10):
        log.append(kind="reflection", content=payload, meta={})

    tendencies = mirror.rsm_snapshot()["behavioral_tendencies"]
    assert tendencies.get("instantiation_capacity") == 20


def _synthetic_events_with_prefix_uniqueness(unique_prefixes: int, total: int):
    events = []
    # Build 'unique_prefixes' distinct 8-char hex prefixes
    prefixes = [f"{i:08x}" for i in range(unique_prefixes)]
    # Ensure total events; reuse the first prefix for duplicates
    for i in range(total):
        pre = prefixes[i % unique_prefixes]
        # Expand to 64 hex chars to mimic sha256
        h = (pre * 8)[:64]
        events.append(
            {
                "id": i + 1,
                "ts": "2020-01-01T00:00:00.000000Z",
                "kind": "test_event",
                "content": "x",
                "meta": {},
                "prev_hash": None,
                "hash": h,
            }
        )
    return events


def test_rsm_uniqueness_emphasis_score_from_hash_prefixes():
    rsm = RecursiveSelfModel()
    events = _synthetic_events_with_prefix_uniqueness(unique_prefixes=80, total=100)
    rsm.rebuild(events)
    snap = rsm.snapshot()
    tendencies = snap["behavioral_tendencies"]
    assert tendencies.get("uniqueness_emphasis") == 8

    # Rebuild parity through LedgerMirror using real EventLog still yields deterministic value
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)
    # Feed synthetic events through sync; RSM ignores out-of-order ids and updates deterministically
    for ev in events:
        mirror.sync(ev)
    assert mirror.rsm_snapshot()["behavioral_tendencies"]["uniqueness_emphasis"] == 8


def test_rsm_uniqueness_caps_and_edges():
    # All unique within 10 events -> score 10
    rsm = RecursiveSelfModel()
    rsm.rebuild(_synthetic_events_with_prefix_uniqueness(unique_prefixes=10, total=10))
    assert rsm.snapshot()["behavioral_tendencies"]["uniqueness_emphasis"] == 10

    # All same within 10 events -> score 1
    rsm2 = RecursiveSelfModel()
    rsm2.rebuild(_synthetic_events_with_prefix_uniqueness(unique_prefixes=1, total=10))
    assert rsm2.snapshot()["behavioral_tendencies"]["uniqueness_emphasis"] == 1


def test_diff_rsm_same_id_returns_empty():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    log.append(
        kind="assistant_message",
        content="Determinism ensures stable behavior.",
        meta={},
    )
    event_id = log.read_all()[-1]["id"]

    diff = mirror.diff_rsm(event_id, event_id)
    assert diff == {
        "tendencies_delta": {},
        "gaps_added": [],
        "gaps_resolved": [],
    }
