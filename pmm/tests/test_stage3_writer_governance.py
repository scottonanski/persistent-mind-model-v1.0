from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from pmm.core.event_log import (
    EventLog,
    PostCommitProjectionError,
    ProjectionBarrierError,
)
from pmm.core.writer_session import (
    WriterClockAnomaly,
    WriterOwnershipBusy,
    WriterOwnershipConflict,
    WriterOwnershipLost,
)
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.mcp_server import pmm_turn


class _CompleteAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return "complete"


class _SlowAdapter:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        time.sleep(self.delay)
        return "complete after heartbeat"


class _LoseOwnershipAdapter:
    def __init__(self, log: EventLog) -> None:
        self.log = log

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        assert self.log.writer_session is not None
        self.log.writer_session.mark_unhealthy("simulated heartbeat loss")
        return "stale provider result"


class _TrackingAdapter:
    def __init__(self) -> None:
        self.called = False

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        self.called = True
        return "must not run"


class _BlockingAdapter:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        self.entered.set()
        assert self.release.wait(timeout=5)
        return "completed by live owner"


def _start_owner_process(path: str, ready_path: Path) -> subprocess.Popen[str]:
    script = (
        "import pathlib,sys\n"
        "from pmm.core.event_log import EventLog\n"
        "log=EventLog(sys.argv[1], writer_role='holder-process')\n"
        "pathlib.Path(sys.argv[2]).write_text('ready')\n"
        "sys.stdin.read()\n"
        "log.close()\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, path, str(ready_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5
    while not ready_path.exists() and process.poll() is None:
        if time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    assert ready_path.exists(), process.stderr.read() if process.stderr else ""
    return process


def test_live_writer_excludes_contender_and_clean_release_advances_fence(
    tmp_path,
) -> None:
    path = str(tmp_path / "owner.db")
    first = EventLog(path, writer_role="first")
    assert first.writer_session is not None
    first_fence = first.writer_session.fence

    with pytest.raises(WriterOwnershipConflict):
        EventLog(path, writer_role="contender")

    first.close()
    second = EventLog(path, writer_role="second")
    assert second.writer_session is not None
    assert second.writer_session.fence == first_fence + 1
    second.close()


def test_contender_does_not_hide_sqlite_reservation_wait(tmp_path) -> None:
    path = str(tmp_path / "busy-owner.db")
    owner = EventLog(path)
    owner._conn.execute("BEGIN IMMEDIATE")
    started = time.monotonic()
    try:
        with pytest.raises(WriterOwnershipBusy):
            EventLog(path, writer_role="busy-contender")
    finally:
        owner._conn.rollback()
        owner.close()
    assert time.monotonic() - started < 0.5


def test_trigger_rejects_unowned_raw_sql_writer(tmp_path) -> None:
    path = str(tmp_path / "trigger.db")
    owner = EventLog(path)
    owner.close()

    raw = sqlite3.connect(path)
    with pytest.raises(sqlite3.OperationalError):
        raw.execute(
            "INSERT INTO events (ts, kind, content, meta, prev_hash, hash) "
            "VALUES ('now', 'test_event', 'raw', '{}', NULL, 'raw-hash')"
        )
    raw.close()


def test_existing_ledger_bootstraps_control_plane_and_trigger_atomically(
    tmp_path,
) -> None:
    path = str(tmp_path / "legacy.db")
    raw = sqlite3.connect(path)
    raw.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, "
        "kind TEXT NOT NULL, content TEXT NOT NULL, meta TEXT NOT NULL, "
        "prev_hash TEXT, hash TEXT)"
    )
    raw.commit()
    raw.close()

    owner = EventLog(path, writer_role="bootstrap")
    owner.append(kind="test_event", content="governed", meta={})
    tables = {
        row[0]
        for row in owner._conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"
        )
    }
    assert {
        "pmm_database_identity",
        "pmm_writer_lease",
        "pmm_projection_status",
        "pmm_events_require_writer",
    }.issubset(tables)
    owner.close()


def test_mcp_one_shot_contender_fails_explicitly_then_acquires_after_release(
    tmp_path,
) -> None:
    path = str(tmp_path / "mcp-contention.db")
    ready_path = tmp_path / "owner.ready"
    owner_process = _start_owner_process(path, ready_path)
    started = time.monotonic()
    try:
        with patch.dict(
            "os.environ",
            {"PMM_MCP_DB": path, "PMM_MCP_MODEL": "dummy"},
            clear=False,
        ):
            with pytest.raises(RuntimeError, match="live writer"):
                pmm_turn("contender", model="dummy")
        assert time.monotonic() - started < 5
    finally:
        assert owner_process.stdin is not None
        owner_process.stdin.close()
        owner_process.wait(timeout=5)

    with patch.dict(
        "os.environ",
        {"PMM_MCP_DB": path, "PMM_MCP_MODEL": "dummy"},
        clear=False,
    ):
        result = pmm_turn("successor", model="dummy")
    assert result["event_range"]["first"] is not None


def test_same_owner_connections_cannot_fork_hash_chain(tmp_path) -> None:
    path = str(tmp_path / "chain.db")
    first = EventLog(path)
    first.append(kind="test_event", content="seed", meta={})
    second = EventLog(path, writer_session=first.writer_session)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def append(log: EventLog, content: str) -> None:
        try:
            barrier.wait()
            log.append(kind="test_event", content=content, meta={})
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [
        threading.Thread(target=append, args=(first, "one")),
        threading.Thread(target=append, args=(second, "two")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    events = first.read_all()
    assert errors == []
    assert all(
        events[index]["prev_hash"] == events[index - 1]["hash"]
        for index in range(1, len(events))
    )
    second.close()
    first.close()


def test_fixed_watermark_catches_event_missed_by_process_local_listener(
    tmp_path,
) -> None:
    path = str(tmp_path / "projection.db")
    primary = EventLog(path)
    runtime = RuntimeLoop(eventlog=primary, adapter=_CompleteAdapter(), autonomy=False)
    shadow = EventLog(path, writer_session=primary.writer_session)
    external_id = shadow.append(kind="user_message", content="external", meta={})

    assert not runtime.memegraph.graph.has_node(external_id)
    assert primary.projection_barrier() >= external_id
    assert runtime.memegraph.graph.has_node(external_id)

    shadow.close()
    primary.close()


def test_required_projection_failure_reports_committed_event_and_poisoned_owner(
    tmp_path,
) -> None:
    path = str(tmp_path / "projection-failure.db")
    log = EventLog(path)

    def fail_projection(event) -> None:
        raise RuntimeError("projection exploded")

    log.register_listener(
        fail_projection,
        name="required.failure",
        required=True,
        applied_through=log.count(),
    )

    with pytest.raises(PostCommitProjectionError) as caught:
        log.append(kind="test_event", content="committed", meta={})

    error = caught.value
    assert error.canonical_commit_succeeded is True
    assert error.canonical_created is True
    assert error.failed_projection == "required.failure"
    assert error.health_record_persisted is True
    assert log.get(error.event_id)["content"] == "committed"
    with pytest.raises(WriterOwnershipLost):
        log.append(kind="test_event", content="must fail", meta={})
    status = log._conn.execute(
        "SELECT state, failed_event_id FROM pmm_projection_status "
        "WHERE projection_name = 'required.failure'"
    ).fetchone()
    assert tuple(status) == ("failed", error.event_id)
    log.close()


def test_postcommit_error_distinguishes_new_commit_from_older_failed_delivery(
    tmp_path,
) -> None:
    path = str(tmp_path / "projection-catchup-failure.db")
    log = EventLog(path)
    older_id = log.append(kind="test_event", content="older", meta={})

    def fail_older(event) -> None:
        if event["id"] == older_id:
            raise RuntimeError("older event cannot project")

    log.register_listener(
        fail_older,
        name="required.catchup-failure",
        required=True,
        applied_through=0,
    )
    expected_new_id = log.count() + 1
    with pytest.raises(PostCommitProjectionError) as caught:
        log.append(kind="test_event", content="new commit", meta={})

    assert caught.value.event_id == expected_new_id
    assert caught.value.failed_event_id == older_id
    assert caught.value.canonical_commit_succeeded is True
    assert log.get(expected_new_id)["content"] == "new commit"
    log.close()


def test_required_projection_rebuild_failure_is_durable_and_fail_closed(
    tmp_path,
) -> None:
    path = str(tmp_path / "projection-rebuild-failure.db")
    log = EventLog(path)
    log.append(kind="test_event", content="seed", meta={})

    def fail_rebuild(events) -> None:
        raise RuntimeError("cannot rebuild projection")

    with pytest.raises(ProjectionBarrierError) as caught:
        log.rebuild_and_register_listener(
            fail_rebuild,
            lambda event: None,
            name="required.rebuild",
            required=True,
        )

    assert caught.value.health_record_persisted is True
    assert log.writer_session is not None and not log.writer_session.healthy
    status = log._conn.execute(
        "SELECT state, failed_event_id FROM pmm_projection_status "
        "WHERE projection_name = 'required.rebuild'"
    ).fetchone()
    assert tuple(status) == ("failed", 1)
    with pytest.raises(WriterOwnershipLost):
        log.append(kind="test_event", content="blocked", meta={})
    log.close()


def test_optional_listener_cannot_swallow_nested_required_delivery_failure(
    tmp_path,
) -> None:
    path = str(tmp_path / "nested-listener-failure.db")
    log = EventLog(path)

    def optional_writer(event) -> None:
        if event["content"] == "parent":
            log.append(kind="test_event", content="nested", meta={})

    def required_failure(event) -> None:
        if event["content"] == "nested":
            raise RuntimeError("nested required failure")

    log.register_listener(optional_writer, name="optional.writer")
    log.register_listener(
        required_failure,
        name="required.nested",
        required=True,
        applied_through=log.count(),
    )

    with pytest.raises(PostCommitProjectionError) as caught:
        log.append(kind="test_event", content="parent", meta={})

    assert log.get(caught.value.event_id)["content"] == "nested"
    assert [event["content"] for event in log.read_all()] == ["parent", "nested"]
    assert log.writer_session is not None and not log.writer_session.healthy
    log.close()


def test_required_projection_failure_stops_generation_after_user_commit(
    tmp_path,
) -> None:
    path = str(tmp_path / "projection-stops-generation.db")
    log = EventLog(path)
    adapter = _TrackingAdapter()
    runtime = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)

    def fail_projection(event) -> None:
        raise RuntimeError("required graph unavailable")

    log.register_listener(
        fail_projection,
        name="required.after-startup",
        required=True,
        applied_through=log.count(),
    )
    with pytest.raises(PostCommitProjectionError):
        runtime.run_turn("commit user event only")

    assert adapter.called is False
    assert len(log.read_by_kind("user_message")) == 1
    assert log.read_by_kind("assistant_message") == []
    assert log.read_by_kind("generation_failure") == []
    log.close()


def test_recovery_waits_for_required_projection_health(tmp_path) -> None:
    path = str(tmp_path / "recovery-barrier.db")
    log = EventLog(path)
    user_id = log.append(
        kind="user_message",
        content="interrupted",
        meta={"role": "user", "turn_protocol": "terminal_outcome.v1"},
    )

    def fail_projection(event) -> None:
        raise RuntimeError("recovery projection unavailable")

    log.register_listener(
        fail_projection,
        name="required.before-recovery",
        required=True,
        applied_through=0,
    )
    with pytest.raises(ProjectionBarrierError, match="required.before-recovery"):
        RuntimeLoop(eventlog=log, adapter=_CompleteAdapter(), autonomy=False)

    assert log.get(user_id) is not None
    assert log.read_by_kind("generation_failure") == []
    log.close()


def test_contender_cannot_recover_a_live_turn(tmp_path) -> None:
    path = str(tmp_path / "live-turn-recovery.db")
    log = EventLog(path, writer_role="live-turn")
    adapter = _BlockingAdapter()
    runtime = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)
    errors: list[Exception] = []

    def run_live_turn() -> None:
        try:
            runtime.run_turn("still generating")
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    thread = threading.Thread(target=run_live_turn)
    thread.start()
    assert adapter.entered.wait(timeout=2)
    with pytest.raises(WriterOwnershipConflict):
        EventLog(path, writer_role="recovery-contender")

    adapter.release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert log.read_by_kind("generation_failure") == []
    assert len(log.read_by_kind("assistant_message")) == 1
    log.close()


def test_heartbeat_remains_live_during_provider_generation(tmp_path) -> None:
    path = str(tmp_path / "heartbeat.db")
    log = EventLog(path, lease_seconds=0.3, heartbeat_seconds=0.05)
    runtime = RuntimeLoop(eventlog=log, adapter=_SlowAdapter(0.6), autonomy=False)

    runtime.run_turn("keep ownership alive")

    assert len(log.read_by_kind("assistant_message")) == 1
    assert log.writer_session is not None and log.writer_session.healthy
    log.close()


def test_provider_result_is_discarded_after_ownership_loss(tmp_path) -> None:
    path = str(tmp_path / "discard.db")
    log = EventLog(path)
    runtime = RuntimeLoop(
        eventlog=log, adapter=_LoseOwnershipAdapter(log), autonomy=False
    )

    with pytest.raises(WriterOwnershipLost):
        runtime.run_turn("lose ownership")

    assert len(log.read_by_kind("user_message")) == 1
    assert log.read_by_kind("assistant_message") == []
    assert log.read_by_kind("generation_failure") == []
    log.close()


def test_expired_owner_is_fenced_after_takeover(tmp_path) -> None:
    path = str(tmp_path / "takeover.db")
    old = EventLog(path, lease_seconds=0.2, heartbeat_seconds=0.05)
    assert old.writer_session is not None
    old_fence = old.writer_session.fence
    old.writer_session._stop.set()
    assert old.writer_session._heartbeat_thread is not None
    old.writer_session._heartbeat_thread.join(timeout=1)
    time.sleep(0.25)

    new = EventLog(path)
    assert new.writer_session is not None
    assert new.writer_session.fence == old_fence + 1
    with pytest.raises(WriterOwnershipLost):
        old.append(kind="test_event", content="stale", meta={})

    old.close()
    new.append(kind="test_event", content="current", meta={})
    new.close()


def test_database_clock_rollback_signal_fails_owner_closed(tmp_path) -> None:
    path = str(tmp_path / "clock-anomaly.db")
    log = EventLog(path)
    assert log.writer_session is not None
    log.writer_session._stop.set()
    if log.writer_session._heartbeat_thread is not None:
        log.writer_session._heartbeat_thread.join(timeout=1)

    raw = sqlite3.connect(path)
    raw.execute(
        "UPDATE pmm_writer_lease SET last_db_time = last_db_time + 60 "
        "WHERE singleton = 1"
    )
    raw.commit()
    raw.close()

    with pytest.raises(WriterClockAnomaly):
        log.append(kind="test_event", content="clock moved backwards", meta={})
    assert not log.writer_session.healthy
    log.close()
