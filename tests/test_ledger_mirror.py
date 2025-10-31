from __future__ import annotations

from unittest.mock import Mock

from pmm.runtime.context_builder import build_context_from_ledger
from pmm.runtime.ledger_mirror import LedgerMirror
from pmm.runtime.memegraph import MemeGraphProjection
from pmm.storage.eventlog import EventLog


def test_ledger_mirror_prefers_graph_indices_for_tail() -> None:
    eventlog = Mock()
    eventlog.read_by_ids.return_value = [{"id": 2}, {"id": 3}]
    eventlog.read_tail.return_value = [{"id": 99}]
    memegraph = Mock()
    memegraph.event_ids.return_value = [1, 2, 3]
    memegraph.open_commitments_snapshot.return_value = {}

    mirror = LedgerMirror(eventlog, memegraph)

    first = mirror.read_tail(limit=2)
    second = mirror.read_tail(limit=2)

    assert first == second == [{"id": 2}, {"id": 3}]
    eventlog.read_by_ids.assert_called_once_with([3, 2])
    eventlog.read_tail.assert_not_called()


def test_mirror_open_commitment_events_returns_ledger_payload(tmp_path) -> None:
    db_path = tmp_path / "mirror.db"
    log = EventLog(str(db_path))
    log.append(
        kind="identity_adopt",
        content="Persistent Mind Model",
        meta={"name": "Persistent Mind Model", "sanitized": "Persistent Mind Model"},
    )
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": "CID123", "text": "Document mirror layer"},
    )

    memegraph = MemeGraphProjection(log)
    mirror = LedgerMirror(log, memegraph)

    events = mirror.get_open_commitment_events()

    assert events, "expected open commitment events"
    assert events[0]["kind"] == "commitment_open"
    assert (events[0].get("meta") or {}).get("cid") == "CID123"


def test_context_builder_matches_with_mirror(tmp_path) -> None:
    db_path = tmp_path / "context.db"
    log = EventLog(str(db_path))
    log.append(
        kind="identity_adopt",
        content="PMM Alpha",
        meta={"name": "PMM Alpha", "sanitized": "PMM Alpha"},
    )
    log.append(
        kind="commitment_open",
        content="",
        meta={"cid": "CID42", "text": "Ship mirror support"},
    )

    memegraph = MemeGraphProjection(log)
    mirror = LedgerMirror(log, memegraph)

    kwargs = dict(
        memegraph=memegraph,
        snapshot=None,
        n_reflections=3,
        use_tail_optimization=True,
        max_commitment_chars=400,
        max_reflection_chars=600,
        compact_mode=False,
        include_metrics=False,
        include_commitments=True,
        include_reflections=False,
    )

    raw = build_context_from_ledger(log, **kwargs)
    mirrored = build_context_from_ledger(log, mirror=mirror, **kwargs)

    assert raw == mirrored
