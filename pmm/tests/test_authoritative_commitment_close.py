# SPDX-License-Identifier: PMM-1.0

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from pmm.core.commitment_manager import CommitmentManager
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.core.mirror import Mirror


def _open(log: EventLog, cid: str = "c1") -> int:
    return log.append(
        kind="commitment_open",
        content=f"Commitment opened: {cid}",
        meta={"cid": cid, "source": "assistant", "text": cid},
    )


def test_unknown_cid_does_not_create_canonical_close() -> None:
    log = EventLog(":memory:")

    with pytest.raises(ValueError, match="commitment is not open"):
        log.append(
            kind="commitment_close",
            content="Commitment closed: missing",
            meta={"cid": "missing", "source": "assistant"},
        )

    assert log.read_by_kind("commitment_close") == []
    assert CommitmentManager(log).close_commitment("missing") is None
    assert log.read_by_kind("commitment_close") == []


def test_close_records_source_and_exact_open_event() -> None:
    log = EventLog(":memory:")
    open_event_id = _open(log)

    close_event_id = CommitmentManager(log).close_commitment(
        "c1", source="autonomy_kernel", reason="bounded_test"
    )

    close_event = log.get(close_event_id or 0)
    assert close_event is not None
    assert close_event["meta"] == {
        "cid": "c1",
        "open_event_id": open_event_id,
        "reason": "bounded_test",
        "source": "autonomy_kernel",
    }
    assert not Mirror(log).is_commitment_open("c1")

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    assert graph.graph[close_event_id][open_event_id]["label"] == "closes"


def test_second_close_is_idempotent() -> None:
    log = EventLog(":memory:")
    _open(log)

    first = log.append(
        kind="commitment_close",
        content="first",
        meta={"cid": "c1", "source": "assistant"},
    )
    second = log.append(
        kind="commitment_close",
        content="second attempt",
        meta={"cid": "c1", "source": "autonomy_kernel"},
    )

    assert second == first
    assert [event["id"] for event in log.read_by_kind("commitment_close")] == [first]


def test_concurrent_closes_create_one_event(tmp_path) -> None:
    db_path = str(tmp_path / "commitments.db")
    first_log = EventLog(db_path)
    second_log = EventLog(db_path, writer_session=first_log.writer_session)
    open_event_id = _open(first_log)

    def close(log: EventLog, source: str) -> int:
        return log.append(
            kind="commitment_close",
            content=f"closed by {source}",
            meta={"cid": "c1", "source": source},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: close(*args),
                [(first_log, "assistant"), (second_log, "autonomy_kernel")],
            )
        )

    closes = first_log.read_by_kind("commitment_close")
    assert len(closes) == 1
    assert results == [closes[0]["id"], closes[0]["id"]]
    assert closes[0]["meta"]["open_event_id"] == open_event_id
    second_log.close()
    first_log.close()
