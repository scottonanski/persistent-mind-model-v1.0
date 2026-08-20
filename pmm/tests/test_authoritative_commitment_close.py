# SPDX-License-Identifier: PMM-1.0

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from pmm.core.commitment_manager import CommitmentManager
from pmm.core.event_log import EventLog, _canonical_json
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
        meta={"cid": "c1", "source": "autonomy_kernel"},
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
    first_assistant = first_log.append(
        kind="assistant_message", content="CLOSE: c1", meta={"role": "assistant"}
    )
    second_assistant = first_log.append(
        kind="assistant_message", content="CLOSE: c1", meta={"role": "assistant"}
    )

    def close(log: EventLog, origin_event_id: int) -> tuple[int | None, bool]:
        return CommitmentManager(log).close_commitment_status(
            "c1",
            source="assistant",
            origin_event_id=origin_event_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: close(*args),
                [
                    (first_log, first_assistant),
                    (second_log, second_assistant),
                ],
            )
        )

    closes = first_log.read_by_kind("commitment_close")
    assert len(closes) == 1
    assert [event_id for event_id, _created in results] == [
        closes[0]["id"],
        closes[0]["id"],
    ]
    assert sum(int(created) for _event_id, created in results) == 1
    assert closes[0]["meta"]["open_event_id"] == open_event_id
    assert closes[0]["meta"]["origin_event_id"] in {
        first_assistant,
        second_assistant,
    }
    second_log.close()
    first_log.close()


def test_assistant_close_requires_matching_post_open_origin() -> None:
    log = EventLog(":memory:")
    prior_assistant = log.append(
        kind="assistant_message",
        content="CLOSE: c1",
        meta={"role": "assistant"},
    )
    open_event_id = _open(log)
    wrong_kind_id = log.append(kind="user_message", content="CLOSE: c1", meta={})
    wrong_text_id = log.append(
        kind="assistant_message",
        content="CLOSE: another",
        meta={"role": "assistant"},
    )

    with pytest.raises(ValueError, match="requires a positive origin_event_id"):
        CommitmentManager(log).close_commitment("c1", source="assistant")
    with pytest.raises(ValueError, match="existing assistant_message"):
        CommitmentManager(log).close_commitment(
            "c1", source="assistant", origin_event_id=wrong_kind_id
        )
    with pytest.raises(ValueError, match="matching CLOSE line"):
        CommitmentManager(log).close_commitment(
            "c1", source="assistant", origin_event_id=wrong_text_id
        )
    with pytest.raises(ValueError, match="must follow the open event"):
        CommitmentManager(log).close_commitment(
            "c1", source="assistant", origin_event_id=prior_assistant
        )
    with pytest.raises(ValueError, match="reserved for assistant-produced closes"):
        CommitmentManager(log).close_commitment(
            "c1", source="autonomy_kernel", origin_event_id=wrong_text_id
        )
    with pytest.raises(ValueError, match="reserved for assistant-produced closes"):
        log.append_commitment_close(
            content="invalid explicit null origin",
            meta={
                "cid": "c1",
                "source": "autonomy_kernel",
                "origin_event_id": None,
            },
        )

    closing_assistant = log.append(
        kind="assistant_message",
        content="Done.\nCLOSE: c1",
        meta={"role": "assistant"},
    )
    close_event_id = CommitmentManager(log).close_commitment(
        "c1", source="assistant", origin_event_id=closing_assistant
    )

    close_event = log.get(close_event_id or 0)
    assert close_event is not None
    assert close_event["meta"]["open_event_id"] == open_event_id
    assert close_event["meta"]["origin_event_id"] == closing_assistant

    rebuilt = MemeGraph(log)
    rebuilt.rebuild(log.read_all())
    incremental = MemeGraph(log)
    for event in log.read_all():
        incremental.add_event(event)

    for graph in (rebuilt, incremental):
        assert graph.graph[close_event_id][closing_assistant]["label"] == "issued_by"
        assert graph.cids_for_event(closing_assistant) == ["c1"]
        assert closing_assistant in graph.thread_for_cid("c1")
    assert sorted(rebuilt.graph.edges(data="label")) == sorted(
        incremental.graph.edges(data="label")
    )
    assert rebuilt.thread_for_cid("c1") == incremental.thread_for_cid("c1")


def test_idempotent_close_does_not_replace_canonical_origin() -> None:
    log = EventLog(":memory:")
    _open(log)
    first_assistant = log.append(
        kind="assistant_message", content="CLOSE: c1", meta={"role": "assistant"}
    )
    manager = CommitmentManager(log)
    first_close, first_created = manager.close_commitment_status(
        "c1", source="assistant", origin_event_id=first_assistant
    )
    second_assistant = log.append(
        kind="assistant_message", content="CLOSE: c1", meta={"role": "assistant"}
    )

    second_close, second_created = manager.close_commitment_status(
        "c1", source="assistant", origin_event_id=second_assistant
    )

    assert second_close == first_close
    assert first_created is True
    assert second_created is False
    assert log.get(first_close or 0)["meta"]["origin_event_id"] == first_assistant
    assert len(log.read_by_kind("commitment_close")) == 1


def test_same_assistant_may_open_and_close_without_duplicate_thread_node() -> None:
    log = EventLog(":memory:")
    assistant_id = log.append(
        kind="assistant_message",
        content="COMMIT: short task\nCLOSE: c1",
        meta={"role": "assistant"},
    )
    open_event_id = log.append(
        kind="commitment_open",
        content="Commitment opened: short task",
        meta={
            "cid": "c1",
            "origin": "assistant",
            "source": "assistant",
            "text": "short task",
            "origin_event_id": assistant_id,
        },
    )
    close_event_id = CommitmentManager(log).close_commitment(
        "c1", source="assistant", origin_event_id=assistant_id
    )

    rebuilt = MemeGraph(log)
    rebuilt.rebuild(log.read_all())
    incremental = MemeGraph(log)
    for event in log.read_all():
        incremental.add_event(event)

    for graph in (rebuilt, incremental):
        assert graph.graph[close_event_id][assistant_id]["label"] == "issued_by"
        assert graph.cids_for_event(assistant_id) == ["c1"]
        assert graph.thread_for_cid("c1") == [
            assistant_id,
            open_event_id,
            close_event_id,
        ]


def test_apply_closures_reports_only_newly_created_cids() -> None:
    log = EventLog(":memory:")
    _open(log)
    assistant_id = log.append(
        kind="assistant_message", content="CLOSE: c1", meta={"role": "assistant"}
    )
    manager = CommitmentManager(log)

    assert manager.apply_closures(
        ["c1"], source="assistant", origin_event_id=assistant_id
    ) == ["c1"]
    assert (
        manager.apply_closures(["c1"], source="assistant", origin_event_id=assistant_id)
        == []
    )


def test_malformed_explicit_close_relationships_do_not_fall_back() -> None:
    log = EventLog(":memory:")
    open_event_id = _open(log)
    close_event_id = CommitmentManager(log).close_commitment(
        "c1", source="autonomy_kernel"
    )
    close_event = log.get(close_event_id or 0)
    assert close_event is not None
    malformed_meta = {
        **close_event["meta"],
        "open_event_id": 9998,
        "origin_event_id": 9999,
    }
    with log._lock:
        log._conn.execute(
            "UPDATE events SET meta = ? WHERE id = ?",
            (_canonical_json(malformed_meta), close_event_id),
        )

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())

    assert not graph.graph.has_edge(close_event_id, open_event_id)
    assert list(graph.graph.successors(close_event_id)) == []
