# SPDX-License-Identifier: PMM-1.0

"""One active commitment_open per CID, enforced inside EventLog."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1, sha256

import pytest

from pmm.core.commitment_manager import CommitmentManager
from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog, _canonical_json
from pmm.core.meme_graph import MemeGraph
from pmm.core.mirror import Mirror
from pmm.retrieval.pipeline import RetrievalResult
from pmm.runtime.context_renderer import _render_threads
from pmm.runtime.loop import RuntimeLoop

LEGACY_TS = "2024-01-01T00:00:00.000000Z"


def _open(log: EventLog, cid: str = "c1", *, content: str | None = None) -> int:
    return log.append(
        kind="commitment_open",
        content=content or f"Commitment opened: {cid}",
        meta={"cid": cid, "source": "assistant", "text": cid},
    )


def _close(log: EventLog, cid: str = "c1", *, source: str = "assistant") -> int:
    return log.append(
        kind="commitment_close",
        content=f"Commitment closed: {cid}",
        meta={"cid": cid, "source": source},
    )


def _insert_legacy_open(log: EventLog, cid: str, *, content: str) -> int:
    """Insert a commitment_open directly, reproducing legacy duplicate history.

    The guarded path can no longer produce competing opens, so an already
    written ledger is simulated by writing the row underneath it.
    """

    meta = _canonical_json({"cid": cid, "source": "assistant", "text": cid})
    digest = sha256(f"legacy:{cid}:{content}".encode("utf-8")).hexdigest()
    with log._lock:
        cur = log._conn.execute(
            "INSERT INTO events (ts, kind, content, meta, prev_hash, hash) "
            "VALUES (?, 'commitment_open', ?, ?, NULL, ?)",
            (LEGACY_TS, content, meta, digest),
        )
    return int(cur.lastrowid)


class ReplySequenceAdapter:
    def __init__(self, replies: list[str]) -> None:
        self.replies = iter(replies)

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return next(self.replies)


def _opened_commitment_reflections(log: EventLog):
    return [
        event
        for event in log.read_by_kind("reflection")
        if "Opened commitments:" in str(event.get("content") or "")
    ]


def test_open_commitment_status_reports_created_and_preserves_str_wrapper() -> None:
    log = EventLog(":memory:")
    manager = CommitmentManager(log)

    assert manager.open_commitment_status("  ") == ("", False)
    assert manager.open_commitment("  ") == ""

    cid, created = manager.open_commitment_status("ship the audit", source="assistant")
    assert created is True
    assert isinstance(cid, str) and cid

    reused = manager.open_commitment("ship the audit", source="assistant")
    assert reused == cid
    assert isinstance(reused, str)
    _reuse_cid, reuse_created = manager.open_commitment_status(
        "ship the audit", source="assistant"
    )
    assert _reuse_cid == cid
    assert reuse_created is False
    assert len(log.read_by_kind("commitment_open")) == 1

    manager.close_commitment(cid, source="assistant")
    reopened_cid, reopened = manager.open_commitment_status(
        "ship the audit", source="assistant"
    )
    assert reopened_cid == cid
    assert reopened is True
    assert len(log.read_by_kind("commitment_open")) == 2


def test_runtime_opened_reflection_tracks_canonical_create_not_rediscovery() -> None:
    text = "same_relation"
    cid = sha1(text.encode("utf-8")).hexdigest()[:8]
    log = EventLog(":memory:")
    loop = RuntimeLoop(
        eventlog=log,
        adapter=ReplySequenceAdapter(
            [
                "Answer.\nCOMMIT: same_relation",
                '{"concepts":["identity.continuity"]}\nRefined.\nCOMMIT: same_relation',
                f"Done.\nCLOSE: {cid}",
                "Again.\nCOMMIT: same_relation",
            ]
        ),
        autonomy=False,
    )

    loop.run_turn("first")
    first_assistant = log.read_by_kind("assistant_message")[0]
    opens = log.read_by_kind("commitment_open")
    assert len(opens) == 1
    assert opens[0]["meta"]["cid"] == cid
    assert opens[0]["meta"]["origin_event_id"] == first_assistant["id"]
    opened = _opened_commitment_reflections(log)
    assert len(opened) == 1
    assert cid in opened[0]["content"]

    loop.run_turn("second")
    assert len(log.read_by_kind("commitment_open")) == 1
    assert len(_opened_commitment_reflections(log)) == 1

    graph = ConceptGraph(log)
    graph.rebuild()
    attributions = graph.attributions_for_thread_binding("identity.continuity", cid)
    model = next(
        item for item in attributions if item["binding_origin"] == "model_declared"
    )
    second_assistant = log.read_by_kind("assistant_message")[1]
    assert model["origin_event_id"] == second_assistant["id"]
    assert opens[0]["id"] < second_assistant["id"]

    loop.run_turn("close")
    loop.run_turn("reopen")
    reopened = log.read_by_kind("commitment_open")
    reopening_assistant = log.read_by_kind("assistant_message")[-1]
    assert len(reopened) == 2
    assert all(event["meta"]["cid"] == cid for event in reopened)
    assert reopened[-1]["meta"]["origin_event_id"] == reopening_assistant["id"]
    opened_after_reopen = _opened_commitment_reflections(log)
    assert len(opened_after_reopen) == 2
    assert all(cid in event["content"] for event in opened_after_reopen)

    latest_open_id = reopened[-1]["id"]
    graph = loop.memegraph
    assert graph.graph[latest_open_id][reopening_assistant["id"]]["label"] == (
        "commits_to"
    )
    assert not graph.graph.has_edge(latest_open_id, first_assistant["id"])
    current_thread = graph.thread_for_cid(cid)
    assert reopening_assistant["id"] in current_thread
    assert first_assistant["id"] not in current_thread
    assert opens[0]["id"] not in current_thread

    rebuilt = MemeGraph(log)
    rebuilt.rebuild(log.read_all())
    assert rebuilt.thread_for_cid(cid) == current_thread
    assert rebuilt.cids_for_event(reopening_assistant["id"]) == [cid]
    assert rebuilt.cids_for_event(first_assistant["id"]) == [cid]


def test_commitment_open_origin_reference_is_enforced() -> None:
    log = EventLog(":memory:")
    user_id = log.append(kind="user_message", content="please commit", meta={})
    assistant_id = log.append(
        kind="assistant_message",
        content="I will.\nCOMMIT: ship the audit",
        meta={"role": "assistant"},
    )
    base_meta = {
        "cid": "c1",
        "origin": "assistant",
        "source": "assistant",
        "text": "ship the audit",
    }

    with pytest.raises(ValueError, match="positive integer"):
        log.append(
            kind="commitment_open",
            content="bad origin type",
            meta={**base_meta, "origin_event_id": True},
        )
    with pytest.raises(ValueError, match="positive integer"):
        log.append(
            kind="commitment_open",
            content="null origin",
            meta={**base_meta, "origin_event_id": None},
        )
    with pytest.raises(ValueError, match="requires assistant origin"):
        log.append(
            kind="commitment_open",
            content="user cannot claim assistant origin",
            meta={
                **base_meta,
                "origin": "user",
                "source": "user",
                "origin_event_id": assistant_id,
            },
        )
    with pytest.raises(ValueError, match="existing assistant_message"):
        log.append(
            kind="commitment_open",
            content="wrong origin kind",
            meta={**base_meta, "origin_event_id": user_id},
        )
    with pytest.raises(ValueError, match="matching COMMIT line"):
        log.append(
            kind="commitment_open",
            content="wrong origin text",
            meta={**base_meta, "text": "different", "origin_event_id": assistant_id},
        )

    created = log.append(
        kind="commitment_open",
        content="valid explicit origin",
        meta={**base_meta, "origin_event_id": assistant_id},
    )
    assert log.get(created)["meta"]["origin_event_id"] == assistant_id

    with pytest.raises(ValueError, match="reserved for commitment_open"):
        log.append(
            kind="commitment_close",
            content="invalid close metadata",
            meta={
                "cid": "c1",
                "source": "assistant",
                "origin_event_id": assistant_id,
            },
        )


def test_explicit_origin_does_not_fall_back_when_legacy_row_is_malformed() -> None:
    log = EventLog(":memory:")
    first_assistant = log.append(
        kind="assistant_message",
        content="COMMIT: same",
        meta={},
    )
    malformed_open = _insert_legacy_open(log, "c1", content="legacy malformed")
    with log._lock:
        meta = _canonical_json(
            {
                "cid": "c1",
                "origin": "assistant",
                "source": "assistant",
                "text": "same",
                "origin_event_id": 9999,
            }
        )
        log._conn.execute(
            "UPDATE events SET meta = ? WHERE id = ?",
            (meta, malformed_open),
        )

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())

    assert not graph.graph.has_edge(malformed_open, first_assistant)
    assert list(graph.graph.successors(malformed_open)) == []


def test_repeated_general_open_writes_one_canonical_open() -> None:
    log = EventLog(":memory:")
    manager = CommitmentManager(log)

    first_cid = manager.open_commitment("ship the audit", source="assistant")
    second_cid = manager.open_commitment("ship the audit", source="assistant")

    assert first_cid == second_cid
    assert first_cid
    opens = log.read_by_kind("commitment_open")
    assert len(opens) == 1
    assert opens[0]["meta"]["cid"] == first_cid


def test_direct_generic_append_cannot_bypass_guard() -> None:
    log = EventLog(":memory:")

    first = _open(log)
    second = log.append(
        kind="commitment_open",
        content="a different content body for the same cid",
        meta={"cid": "c1", "source": "autonomy_kernel", "text": "other"},
    )

    assert second == first
    assert [event["id"] for event in log.read_by_kind("commitment_open")] == [first]
    # The no-op returns the stored open, not the rejected candidate's meta.
    assert log.get(first)["meta"]["source"] == "assistant"


def test_open_requires_non_empty_cid() -> None:
    log = EventLog(":memory:")

    with pytest.raises(ValueError, match="commitment_open requires non-empty cid"):
        log.append(kind="commitment_open", content="c", meta={"source": "assistant"})

    assert log.read_by_kind("commitment_open") == []


def test_concurrent_identical_opens_create_one_event(tmp_path) -> None:
    db_path = str(tmp_path / "commitments.db")
    first_log = EventLog(db_path)
    second_log = EventLog(db_path, writer_session=first_log.writer_session)

    def open_it(log: EventLog, source: str) -> int:
        return log.append(
            kind="commitment_open",
            content=f"opened by {source}",
            meta={"cid": "c1", "source": source, "text": "c1"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: open_it(*args),
                [(first_log, "assistant"), (second_log, "autonomy_kernel")],
            )
        )

    opens = first_log.read_by_kind("commitment_open")
    assert len(opens) == 1
    assert results == [opens[0]["id"], opens[0]["id"]]
    second_log.close()
    first_log.close()


def test_close_then_reopen_creates_a_new_open() -> None:
    log = EventLog(":memory:")

    first_open = _open(log)
    close_id = _close(log)
    second_open = _open(log)

    assert second_open != first_open
    assert second_open > close_id
    assert [event["id"] for event in log.read_by_kind("commitment_open")] == [
        first_open,
        second_open,
    ]
    assert log.get(close_id)["meta"]["open_event_id"] == first_open
    assert Mirror(log).is_commitment_open("c1")

    # A repeat open after the reopen is a no-op again.
    assert _open(log) == second_open
    assert len(log.read_by_kind("commitment_open")) == 2


def _legacy_duplicate_open_ledger(log: EventLog) -> tuple[int, int, int]:
    """Build a legacy ledger with two opens for one cid plus its close."""

    log.append(kind="user_message", content="hello", meta={"role": "user"})
    stale_open = _insert_legacy_open(log, "c1", content="legacy open one")
    latest_open = _insert_legacy_open(log, "c1", content="legacy open two")
    close_id = _close(log)
    return stale_open, latest_open, close_id


def test_legacy_duplicate_opens_resolve_latest_open() -> None:
    log = EventLog(":memory:")
    stale_open, latest_open, close_id = _legacy_duplicate_open_ledger(log)

    assert latest_open > stale_open
    # The authoritative close transitions from the latest open, matching Mirror.
    assert log.get(close_id)["meta"]["open_event_id"] == latest_open
    assert not Mirror(log).is_commitment_open("c1")

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())

    assert graph._find_commitment_open_by_cid("c1") == latest_open
    thread = graph.thread_for_cid("c1")
    assert latest_open in thread
    assert close_id in thread
    assert stale_open not in thread
    assert graph.graph[close_id][latest_open]["label"] == "closes"


def test_legacy_duplicate_opens_render_closed_thread() -> None:
    log = EventLog(":memory:")
    _legacy_duplicate_open_ledger(log)

    graph = MemeGraph(log)
    graph.rebuild(log.read_all())
    concepts = ConceptGraph(log)
    result = RetrievalResult(event_ids=[], relevant_cids=["c1"], active_concepts=[])

    rendered = _render_threads(result, graph, concepts, log)

    assert "- c1: Closed" in rendered
    assert "- c1: Active" not in rendered


def test_rebuild_and_incremental_agree_for_duplicate_open_lifecycle() -> None:
    log = EventLog(":memory:")
    _legacy_duplicate_open_ledger(log)
    _open(log, "c1")  # reopen after the close
    events = log.read_all()

    rebuilt = MemeGraph(log)
    rebuilt.rebuild(events)

    incremental = MemeGraph(log)
    for event in events:
        incremental.add_event(event)

    def _labelled_edges(graph: MemeGraph) -> list[tuple[int, int, str]]:
        return sorted(
            (int(u), int(v), str(data.get("label")))
            for u, v, data in graph.graph.edges(data=True)
        )

    assert sorted(rebuilt.graph.nodes) == sorted(incremental.graph.nodes)
    assert _labelled_edges(rebuilt) == _labelled_edges(incremental)
    assert rebuilt.thread_for_cid("c1") == incremental.thread_for_cid("c1")

    mirror_rebuild = Mirror(log)
    mirror_incremental = Mirror(log, auto_rebuild=False)
    for event in events:
        mirror_incremental.sync(event)

    assert mirror_rebuild.open_commitments == mirror_incremental.open_commitments
    assert mirror_rebuild.is_commitment_open("c1")
