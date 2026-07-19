# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/core/event_log.py
"""SQLite-backed EventLog with simple hash-chain integrity.

Minimal deterministic append/query API for PMM.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable, Dict, List, Optional

from pmm.core.writer_session import (
    WriterOwnershipBusy,
    WriterOwnershipError,
    WriterSession,
)


TERMINAL_OUTCOME_PROTOCOL = "terminal_outcome.v1"
TERMINAL_OUTCOME_KINDS = {"assistant_message", "generation_failure"}


class PostCommitProjectionError(RuntimeError):
    """A canonical event committed but required projection delivery failed."""

    def __init__(
        self,
        *,
        event_id: int,
        failed_event_id: int,
        canonical_created: bool,
        owner_id: str,
        fence: int,
        failed_projection: str,
        last_confirmed_watermark: int,
        health_record_persisted: bool,
        cause: Exception,
    ) -> None:
        self.event_id = event_id
        self.failed_event_id = failed_event_id
        self.canonical_created = canonical_created
        self.canonical_commit_succeeded = canonical_created
        self.owner_id = owner_id
        self.fence = fence
        self.failed_projection = failed_projection
        self.last_confirmed_watermark = last_confirmed_watermark
        self.health_record_persisted = health_record_persisted
        self.cause = cause
        super().__init__(
            f"canonical event {event_id} committed but required projection "
            f"{failed_projection!r} failed at event {failed_event_id}: "
            f"{type(cause).__name__}: {cause}"
        )


class ProjectionBarrierError(RuntimeError):
    """Required projection replay could not confirm a canonical watermark."""

    def __init__(
        self,
        *,
        failed_event_id: int,
        failed_projection: str,
        last_confirmed_watermark: int,
        health_record_persisted: bool,
        cause: Exception,
    ) -> None:
        self.failed_event_id = failed_event_id
        self.failed_projection = failed_projection
        self.last_confirmed_watermark = last_confirmed_watermark
        self.health_record_persisted = health_record_persisted
        self.canonical_commit_succeeded = False
        self.cause = cause
        super().__init__(
            f"required projection {failed_projection!r} failed while replaying "
            f"canonical event {failed_event_id}: {type(cause).__name__}: {cause}"
        )


@dataclass
class _ListenerRegistration:
    name: str
    callback: Callable[[Dict[str, Any]], None]
    required: bool
    applied_through: int = 0


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class EventLog:
    """Persistent append-only log of events with hash chaining."""

    def __init__(
        self,
        path: str = ":memory:",
        *,
        mode: str = "writer",
        writer_session: WriterSession | None = None,
        writer_role: str = "runtime",
        lease_seconds: float = 30.0,
        heartbeat_seconds: float = 5.0,
    ) -> None:
        if mode not in {"reader", "writer"}:
            raise ValueError("EventLog mode must be 'reader' or 'writer'")
        if path != ":memory:":
            path = os.path.abspath(path)
        if mode == "reader" and writer_session is not None:
            raise ValueError("reader EventLog cannot receive a writer session")
        if mode == "reader" and path == ":memory:":
            raise ValueError("reader mode requires a file-backed database")

        self.path = path
        self.mode = mode
        self._closed = False
        self._owns_writer_session = mode == "writer" and writer_session is None
        self.writer_session = writer_session
        if mode == "reader":
            uri_path = f"file:{path}?mode=ro"
            self._conn = sqlite3.connect(
                uri_path,
                uri=True,
                check_same_thread=False,
                isolation_level=None,
                timeout=5.0,
            )
        else:
            self._conn = sqlite3.connect(
                path,
                check_same_thread=False,
                isolation_level=None,
                timeout=5.0,
            )
            # Ownership acquisition is fail-fast. Normal owned operations restore
            # a bounded SQLite busy timeout after the fence has been acquired.
            self._conn.execute("PRAGMA busy_timeout = 0")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._listeners: List[_ListenerRegistration] = []
        self._conn.create_function(
            "pmm_writer_owner",
            0,
            lambda: self.writer_session.owner_id if self.writer_session else None,
        )
        self._conn.create_function(
            "pmm_writer_fence",
            0,
            lambda: self.writer_session.fence if self.writer_session else None,
        )
        if mode == "writer":
            if self.writer_session is None:
                self.writer_session = WriterSession(
                    path=path,
                    role=writer_role,
                    lease_seconds=lease_seconds,
                    heartbeat_seconds=heartbeat_seconds,
                )
            try:
                self._init_db()
                self._conn.execute("PRAGMA busy_timeout = 5000")
                self.writer_session.start_heartbeat()
            except sqlite3.OperationalError as exc:
                self._conn.close()
                self._closed = True
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    raise WriterOwnershipBusy(path) from exc
                raise
            except Exception:
                self._conn.close()
                self._closed = True
                raise

    def _init_db(self) -> None:
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    meta TEXT NOT NULL,
                    prev_hash TEXT,
                    hash TEXT
                );
                """
            )
            # Index to support efficient tail queries (ORDER BY id DESC LIMIT ?).
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_id_desc ON events(id DESC);"
            )
            # Index to support efficient kind-based scans.
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_kind ON events(kind);")
            # Unique index on hash to support idempotent append with INSERT OR IGNORE.
            self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_hash ON events(hash);"
            )
            # New authoritative commitment closures identify exactly one open
            # event. Legacy close records have no open_event_id and remain
            # outside this constraint.
            self._conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_commitment_close_open_event
                ON events(json_extract(meta, '$.open_event_id'))
                WHERE kind = 'commitment_close'
                  AND json_type(meta, '$.open_event_id') = 'integer';
                """)
            # Protocol-v1 turns opt in to exactly one linked terminal outcome.
            # Legacy uses of about_event remain outside this constraint.
            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_terminal_outcome_v1
                ON events(json_extract(meta, '$.about_event'))
                WHERE kind IN ('assistant_message', 'generation_failure')
                  AND json_extract(meta, '$.turn_protocol') = 'terminal_outcome.v1'
                  AND json_type(meta, '$.about_event') = 'integer';
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pmm_database_identity (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    database_uuid TEXT NOT NULL UNIQUE,
                    control_schema_version INTEGER NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pmm_writer_lease (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    owner_id TEXT,
                    fence INTEGER NOT NULL,
                    lease_expires_at REAL NOT NULL,
                    heartbeat_at REAL,
                    last_db_time REAL NOT NULL,
                    owner_pid INTEGER,
                    owner_host TEXT,
                    owner_role TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pmm_projection_status (
                    projection_name TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    fence INTEGER NOT NULL,
                    applied_through INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    failed_event_id INTEGER,
                    error_type TEXT,
                    error_message TEXT,
                    updated_at REAL NOT NULL
                )
                """
            )
            assert self.writer_session is not None
            if self._owns_writer_session:
                self.writer_session.acquire_in_transaction(self._conn)
            else:
                self.writer_session.assert_authority_in_transaction(self._conn)
                identity = self._conn.execute(
                    "SELECT database_uuid FROM pmm_database_identity WHERE singleton = 1"
                ).fetchone()
                if (
                    identity is None
                    or str(identity[0]) != self.writer_session.database_uuid
                ):
                    raise RuntimeError("writer session belongs to a different database")
            self._conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS pmm_events_require_writer
                BEFORE INSERT ON events
                BEGIN
                    SELECT CASE WHEN pmm_writer_owner() IS NULL
                        THEN RAISE(ABORT, 'PMM_WRITER_REQUIRED') END;
                    SELECT CASE WHEN pmm_writer_fence() IS NULL
                        THEN RAISE(ABORT, 'PMM_FENCE_REQUIRED') END;
                    SELECT CASE WHEN NOT EXISTS (
                        SELECT 1 FROM pmm_writer_lease
                        WHERE singleton = 1
                          AND owner_id = pmm_writer_owner()
                          AND fence = pmm_writer_fence()
                          AND lease_expires_at >
                              (julianday('now') - 2440587.5) * 86400.0
                    ) THEN RAISE(ABORT, 'PMM_WRITER_AUTHORITY_LOST') END;
                END
                """
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        if self._closed:
            return
        if self.mode == "writer" and self._owns_writer_session:
            assert self.writer_session is not None
            self.writer_session.release(self._conn)
        self._conn.close()
        self._closed = True

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _require_writer(self) -> WriterSession:
        if self.mode != "writer" or self.writer_session is None:
            raise PermissionError("EventLog is read-only")
        self.writer_session.require_healthy()
        return self.writer_session

    def assert_writer_authority(self) -> None:
        """Confirm the current owner and fence in a reserved database transaction."""
        session = self._require_writer()
        with session.operation(), self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                session.assert_authority_in_transaction(self._conn)
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def register_listener(
        self,
        callback,
        *,
        name: str | None = None,
        required: bool = False,
        applied_through: int = 0,
    ) -> None:
        """Register a callback(event_dict) when an event is appended."""
        with self._lock:
            self._listeners.append(
                _ListenerRegistration(
                    name=name or getattr(callback, "__qualname__", repr(callback)),
                    callback=callback,
                    required=required,
                    applied_through=max(0, int(applied_through)),
                )
            )

    def rebuild_and_register_listener(
        self,
        rebuild: Callable[[List[Dict[str, Any]]], None],
        listener: Callable[[Dict[str, Any]], None],
        *,
        name: str | None = None,
        required: bool = False,
    ) -> None:
        """Rebuild a projection and atomically hand off to incremental updates.

        Holding the EventLog lock across both operations ensures that an append
        is either included in the ordered historical snapshot or delivered to
        the registered listener. If reconstruction fails, the listener is not
        registered and the exception propagates to the caller.
        """

        if self.writer_session is not None:
            with self.writer_session.operation():
                self.assert_writer_authority()
                self._rebuild_and_register_listener_owned(
                    rebuild, listener, name=name, required=required
                )
            return
        self._rebuild_and_register_listener_owned(
            rebuild, listener, name=name, required=required
        )

    def _rebuild_and_register_listener_owned(
        self,
        rebuild: Callable[[List[Dict[str, Any]]], None],
        listener: Callable[[Dict[str, Any]], None],
        *,
        name: str | None,
        required: bool,
    ) -> None:
        registration = _ListenerRegistration(
            name=name or getattr(listener, "__qualname__", repr(listener)),
            callback=listener,
            required=required,
        )
        with self._lock:
            events = self.read_all()
            replayed_through = int(events[-1]["id"]) if events else 0
            try:
                rebuild(events)
            except Exception as exc:
                persisted = self._record_projection_status(
                    registration,
                    state="failed",
                    failed_event_id=replayed_through or None,
                    error=exc,
                )
                if required and self.writer_session is not None:
                    self.writer_session.mark_unhealthy(
                        f"required projection {registration.name} rebuild failed"
                    )
                raise ProjectionBarrierError(
                    failed_event_id=replayed_through,
                    failed_projection=registration.name,
                    last_confirmed_watermark=0,
                    health_record_persisted=persisted,
                    cause=exc,
                ) from exc
            registration.applied_through = replayed_through
            self._listeners.append(registration)

    def _record_projection_status(
        self,
        registration: _ListenerRegistration,
        *,
        state: str,
        failed_event_id: int | None = None,
        error: Exception | None = None,
    ) -> bool:
        if self.mode != "writer" or self.writer_session is None:
            return False
        session = self.writer_session
        try:
            with session.operation(), self._lock:
                self._conn.execute("BEGIN IMMEDIATE")
                now = session.assert_authority_in_transaction(self._conn)
                self._conn.execute(
                    "INSERT INTO pmm_projection_status "
                    "(projection_name, owner_id, fence, applied_through, state, "
                    "failed_event_id, error_type, error_message, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(projection_name) DO UPDATE SET "
                    "owner_id=excluded.owner_id, fence=excluded.fence, "
                    "applied_through=excluded.applied_through, state=excluded.state, "
                    "failed_event_id=excluded.failed_event_id, "
                    "error_type=excluded.error_type, error_message=excluded.error_message, "
                    "updated_at=excluded.updated_at",
                    (
                        registration.name,
                        session.owner_id,
                        session.fence,
                        registration.applied_through,
                        state,
                        failed_event_id,
                        type(error).__name__ if error else None,
                        str(error)[:500] if error else None,
                        now,
                    ),
                )
                self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            return False

    def _deliver_required_through(
        self,
        registration: _ListenerRegistration,
        watermark: int,
        *,
        canonical_created: bool,
        committed_event_id: int | None = None,
    ) -> None:
        while registration.applied_through < watermark:
            events = self.read_range(
                registration.applied_through + 1,
                watermark,
                limit=512,
            )
            if not events:
                registration.applied_through = watermark
                break
            for event in events:
                event_id = int(event["id"])
                try:
                    registration.callback(event)
                except Exception as exc:
                    persisted = self._record_projection_status(
                        registration,
                        state="failed",
                        failed_event_id=event_id,
                        error=exc,
                    )
                    authority = (
                        self.writer_session.authority
                        if self.writer_session is not None
                        else None
                    )
                    if self.writer_session is not None:
                        self.writer_session.mark_unhealthy(
                            f"required projection {registration.name} failed at {event_id}"
                        )
                    if canonical_created:
                        if authority is None:
                            raise RuntimeError(
                                "reader EventLog cannot report a post-commit projection failure"
                            ) from exc
                        raise PostCommitProjectionError(
                            event_id=int(committed_event_id or watermark),
                            failed_event_id=event_id,
                            canonical_created=True,
                            owner_id=authority.owner_id,
                            fence=authority.fence,
                            failed_projection=registration.name,
                            last_confirmed_watermark=registration.applied_through,
                            health_record_persisted=persisted,
                            cause=exc,
                        ) from exc
                    raise ProjectionBarrierError(
                        failed_event_id=event_id,
                        failed_projection=registration.name,
                        last_confirmed_watermark=registration.applied_through,
                        health_record_persisted=persisted,
                        cause=exc,
                    ) from exc
                registration.applied_through = event_id

    def projection_barrier(self, watermark: int | None = None) -> int:
        """Catch every required projection up through a fixed canonical boundary."""
        if self.writer_session is not None:
            with self.writer_session.operation():
                self.assert_writer_authority()
                return self._projection_barrier_owned(watermark)
        return self._projection_barrier_owned(watermark)

    def _projection_barrier_owned(self, watermark: int | None = None) -> int:
        fixed_watermark = self.count() if watermark is None else int(watermark)
        for registration in list(self._listeners):
            if not registration.required:
                continue
            self._deliver_required_through(
                registration,
                fixed_watermark,
                canonical_created=False,
            )
            self._record_projection_status(registration, state="healthy")
        return fixed_watermark

    def _emit(self, ev: Dict[str, Any], *, canonical_created: bool = True) -> None:
        event_id = int(ev["id"])
        for registration in list(self._listeners):
            if event_id <= registration.applied_through:
                continue
            if registration.required:
                self._deliver_required_through(
                    registration,
                    event_id,
                    canonical_created=canonical_created,
                    committed_event_id=event_id if canonical_created else None,
                )
                continue
            try:
                registration.callback(ev)
                registration.applied_through = max(
                    registration.applied_through, event_id
                )
            except (PostCommitProjectionError, WriterOwnershipError):
                raise
            except Exception as exc:
                self._record_projection_status(
                    registration,
                    state="optional_failed",
                    failed_event_id=event_id,
                    error=exc,
                )

    def _last_hash(self) -> Optional[str]:
        with self._lock:
            cur = self._conn.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def append(
        self, *, kind: str, content: str, meta: Optional[Dict[str, Any]] = None
    ) -> int:
        session = self._require_writer()
        with session.operation():
            return self._append_owned(kind=kind, content=content, meta=meta)

    def _append_owned(
        self, *, kind: str, content: str, meta: Optional[Dict[str, Any]] = None
    ) -> int:
        if kind == "commitment_close":
            event_id, _ = self.append_commitment_close(content=content, meta=meta)
            if event_id is None:
                cid = (meta or {}).get("cid")
                raise ValueError(f"commitment is not open: {cid!r}")
            return event_id

        valid_kinds = {
            "user_message",
            "assistant_message",
            "generation_failure",
            "validation_failure",
            "reflection",
            "identity_adoption",
            "meta_summary",
            "metrics_turn",
            "metric_check",
            "commitment_open",
            "commitment_close",
            "claim",
            "autonomy_rule_table",
            "autonomy_tick",
            "autonomy_stimulus",
            "autonomy_kernel",
            "summary_update",
            "inter_ledger_ref",
            "config",
            "filler",
            "test_event",
            "metrics_update",
            "autonomy_metrics",
            "internal_goal_created",
            "retrieval_selection",
            "checkpoint_manifest",
            "embedding_add",
            "lifetime_memory",
            # New kinds introduced by enhancement features
            "stability_metrics",
            "coherence_check",
            "outcome_observation",
            "policy_update",
            "meta_policy_update",
            # Concept Token Layer (CTL) event kinds
            "concept_define",
            "concept_alias",
            "concept_bind_event",
            "concept_relate",
            "concept_state_snapshot",
            "concept_bind_thread",
            # New kinds for Indexer/Archivist
            "claim_from_text",
            "concept_bind_async",
            "violation",
        }
        binding_kinds = {
            "metric_check",
            "autonomy_kernel",
            "internal_goal_created",
            "config",
        }
        if kind in binding_kinds:
            assert kind in binding_kinds, f"Unsupported kind: {kind}"
        if kind not in valid_kinds:
            raise ValueError(f"Invalid event kind: {kind}")
        if not isinstance(content, str):
            raise TypeError("EventLog.append requires string content")
        meta = meta or {}
        if kind in {
            "concept_bind_event",
            "concept_bind_thread",
            "concept_bind_async",
        }:
            from pmm.core.binding_attribution import (
                BINDING_ATTRIBUTION_PROTOCOL,
                validate_binding_attribution_meta,
            )

            validate_binding_attribution_meta(meta)
            if (
                meta.get("binding_protocol") == BINDING_ATTRIBUTION_PROTOCOL
                and meta.get("binding_origin") == "model_declared"
            ):
                origin_event = self.get(int(meta["origin_event_id"]))
                if not origin_event or origin_event.get("kind") != "assistant_message":
                    raise ValueError(
                        "model_declared origin_event_id must identify an assistant_message"
                    )
        # Enforce immutable runtime policy for sensitive kinds
        sensitive = {
            "config",
            "checkpoint_manifest",
            "embedding_add",
            "retrieval_selection",
        }
        if kind in sensitive:
            src = (meta or {}).get("source") or "unknown"
            # Load last policy config
            try:
                policy = None
                # Search from end for last policy
                for e in self.read_all()[::-1]:
                    if e.get("kind") != "config":
                        continue
                    try:
                        data = json.loads(e.get("content") or "{}")
                    except Exception:
                        continue
                    if isinstance(data, dict) and data.get("type") == "policy":
                        policy = data
                        break
                if policy and isinstance(policy.get("forbid_sources"), dict):
                    forbidden = policy["forbid_sources"].get(src)
                    if isinstance(forbidden, list) and kind in forbidden:
                        # Append violation and halt write
                        v_content = f"policy_violation:{src}:{kind}"
                        v_meta = {
                            "source": "runtime",
                            "actor": src,
                            "attempt_kind": kind,
                        }
                        self.append(kind="violation", content=v_content, meta=v_meta)
                        raise PermissionError(f"Policy forbids {src} writing {kind}")
            except (PermissionError, PostCommitProjectionError, WriterOwnershipError):
                raise
            except Exception:
                # Fail-open if policy unreadable
                pass

        session = self._require_writer()
        with session.operation(), self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                session.assert_authority_in_transaction(self._conn)
                row = self._conn.execute(
                    "SELECT hash FROM events ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev_hash = row["hash"] if row and row["hash"] else None
                # Hash payload intentionally excludes timestamp to keep digest
                # stable across independent runs producing identical semantic content.
                payload = {
                    "kind": kind,
                    "content": content,
                    "meta": meta,
                    "prev_hash": prev_hash,
                }
                digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
                ts = _iso_now()
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO events "
                    "(ts, kind, content, meta, prev_hash, hash) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ts, kind, content, _canonical_json(meta), prev_hash, digest),
                )
                if cur.rowcount == 0:
                    canonical_created = False
                    cur_row = self._conn.execute(
                        "SELECT id, ts, kind, content, meta, prev_hash, hash "
                        "FROM events WHERE hash = ?",
                        (digest,),
                    )
                    canonical_row = cur_row.fetchone()
                    if canonical_row is None:
                        raise RuntimeError(
                            "Invariant violation: hash conflict without row"
                        )
                    ev_id = int(canonical_row["id"])
                    ts_db = canonical_row["ts"]
                    kind_db = canonical_row["kind"]
                    content_db = canonical_row["content"]
                    meta_db = json.loads(canonical_row["meta"] or "{}")
                    prev_hash_db = canonical_row["prev_hash"]
                    hash_db = canonical_row["hash"]
                else:
                    canonical_created = True
                    ev_id = int(cur.lastrowid)
                    ts_db = ts
                    kind_db = kind
                    content_db = content
                    meta_db = meta
                    prev_hash_db = prev_hash
                    hash_db = digest
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        ev = {
            "id": ev_id,
            "ts": ts_db,
            "kind": kind_db,
            "content": content_db,
            "meta": meta_db,
            "prev_hash": prev_hash_db,
            "hash": hash_db,
        }
        self._emit(ev, canonical_created=canonical_created)
        return ev_id

    def append_commitment_close(
        self,
        *,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[int], bool]:
        session = self._require_writer()
        with session.operation():
            return self._append_commitment_close_owned(content=content, meta=meta)

    def _append_commitment_close_owned(
        self,
        *,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[int], bool]:
        """Atomically record a successful commitment state transition.

        Returns ``(event_id, created)``. An unknown CID returns ``(None,
        False)``. A CID whose latest lifecycle event is already a close returns
        that close ID with ``created=False``. Every newly created close records
        the exact open event it transitions from.
        """

        if not isinstance(content, str):
            raise TypeError("Commitment close content must be a string")

        close_meta = dict(meta or {})
        cid = close_meta.get("cid")
        if not isinstance(cid, str) or not cid.strip():
            raise ValueError("commitment_close requires non-empty cid")
        cid = cid.strip()

        source = close_meta.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("commitment_close requires non-empty production source")
        source = source.strip()

        session = self._require_writer()
        ts = _iso_now()
        with session.operation(), self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                session.assert_authority_in_transaction(self._conn)
                latest = self._conn.execute(
                    """
                    SELECT id, kind, meta FROM events
                    WHERE kind IN ('commitment_open', 'commitment_close')
                      AND json_extract(meta, '$.cid') = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (cid,),
                ).fetchone()

                if latest is None:
                    self._conn.commit()
                    return None, False
                if latest["kind"] == "commitment_close":
                    self._conn.commit()
                    return int(latest["id"]), False

                open_event_id = int(latest["id"])
                close_meta["cid"] = cid
                close_meta["source"] = source
                close_meta["open_event_id"] = open_event_id

                row = self._conn.execute(
                    "SELECT hash FROM events ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev_hash = row["hash"] if row and row["hash"] else None
                payload = {
                    "kind": "commitment_close",
                    "content": content,
                    "meta": close_meta,
                    "prev_hash": prev_hash,
                }
                digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
                cur = self._conn.execute(
                    "INSERT INTO events "
                    "(ts, kind, content, meta, prev_hash, hash) "
                    "VALUES (?, 'commitment_close', ?, ?, ?, ?)",
                    (ts, content, _canonical_json(close_meta), prev_hash, digest),
                )
                event_id = int(cur.lastrowid)
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        self._emit(
            {
                "id": event_id,
                "ts": ts,
                "kind": "commitment_close",
                "content": content,
                "meta": close_meta,
                "prev_hash": prev_hash,
                "hash": digest,
            }
        )
        return event_id, True

    def append_terminal_outcome(
        self,
        *,
        user_event_id: int,
        kind: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> tuple[int, bool]:
        session = self._require_writer()
        with session.operation():
            return self._append_terminal_outcome_owned(
                user_event_id=user_event_id,
                kind=kind,
                content=content,
                meta=meta,
            )

    def _append_terminal_outcome_owned(
        self,
        *,
        user_event_id: int,
        kind: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> tuple[int, bool]:
        """Atomically append the sole protocol-v1 outcome for a managed turn.

        Returns ``(event_id, created)``. Competing recovery attempts converge on
        the existing outcome under SQLite's write reservation and unique index.
        """

        if kind not in TERMINAL_OUTCOME_KINDS:
            raise ValueError(f"Invalid terminal outcome kind: {kind}")
        if (
            not isinstance(user_event_id, int)
            or isinstance(user_event_id, bool)
            or user_event_id <= 0
        ):
            raise ValueError("user_event_id must be a positive integer")
        if not isinstance(content, str):
            raise TypeError("Terminal outcome content must be a string")

        outcome_meta = dict(meta or {})
        outcome_meta["about_event"] = user_event_id
        outcome_meta["turn_protocol"] = TERMINAL_OUTCOME_PROTOCOL
        meta_json = _canonical_json(outcome_meta)
        session = self._require_writer()
        ts = _iso_now()

        with session.operation(), self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                session.assert_authority_in_transaction(self._conn)
                existing = self._conn.execute(
                    """
                    SELECT id FROM events
                    WHERE kind IN ('assistant_message', 'generation_failure')
                      AND json_extract(meta, '$.turn_protocol') = ?
                      AND json_extract(meta, '$.about_event') = ?
                    ORDER BY id ASC LIMIT 1
                    """,
                    (TERMINAL_OUTCOME_PROTOCOL, user_event_id),
                ).fetchone()
                if existing is not None:
                    self._conn.commit()
                    return int(existing["id"]), False

                row = self._conn.execute(
                    "SELECT hash FROM events ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev_hash = row["hash"] if row and row["hash"] else None
                payload = {
                    "kind": kind,
                    "content": content,
                    "meta": outcome_meta,
                    "prev_hash": prev_hash,
                }
                digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
                cur = self._conn.execute(
                    "INSERT INTO events "
                    "(ts, kind, content, meta, prev_hash, hash) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (ts, kind, content, meta_json, prev_hash, digest),
                )
                event_id = int(cur.lastrowid)
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        self._emit(
            {
                "id": event_id,
                "ts": ts,
                "kind": kind,
                "content": content,
                "meta": outcome_meta,
                "prev_hash": prev_hash,
                "hash": digest,
            }
        )
        return event_id, True

    def read_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM events ORDER BY id ASC")
            out: List[Dict[str, Any]] = []
            for row in cur.fetchall():
                out.append(
                    {
                        "id": row["id"],
                        "ts": row["ts"],
                        "kind": row["kind"],
                        "content": row["content"],
                        "meta": json.loads(row["meta"] or "{}"),
                        "prev_hash": row["prev_hash"],
                        "hash": row["hash"],
                    }
                )
        return out

    def read_tail(self, limit: int) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            rows.reverse()
            out: List[Dict[str, Any]] = []
            for row in rows:
                out.append(
                    {
                        "id": row["id"],
                        "ts": row["ts"],
                        "kind": row["kind"],
                        "content": row["content"],
                        "meta": json.loads(row["meta"] or "{}"),
                        "prev_hash": row["prev_hash"],
                        "hash": row["hash"],
                    }
                )
        return out

    def read_since(self, event_id: int, limit: int) -> List[Dict[str, Any]]:
        """Return events with id > event_id ordered ASC, capped by limit."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
                (int(event_id), int(limit)),
            )
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                out.append(
                    {
                        "id": row["id"],
                        "ts": row["ts"],
                        "kind": row["kind"],
                        "content": row["content"],
                        "meta": json.loads(row["meta"] or "{}"),
                        "prev_hash": row["prev_hash"],
                        "hash": row["hash"],
                    }
                )
        return out

    def read_range(
        self, start_id: int, end_id: int, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Return events between ids inclusive, ordered ASC."""
        params: List[Any] = [int(start_id), int(end_id)]
        sql = "SELECT * FROM events WHERE id >= ? AND id <= ? ORDER BY id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                out.append(
                    {
                        "id": row["id"],
                        "ts": row["ts"],
                        "kind": row["kind"],
                        "content": row["content"],
                        "meta": json.loads(row["meta"] or "{}"),
                        "prev_hash": row["prev_hash"],
                        "hash": row["hash"],
                    }
                )
        return out

    def read_by_kind(
        self, kind: str, limit: Optional[int] = None, reverse: bool = False
    ) -> List[Dict[str, Any]]:
        """Return events filtered by kind, ordered by id."""
        sql = "SELECT * FROM events WHERE kind = ? ORDER BY id ASC"
        params: List[Any] = [kind]
        if reverse:
            sql = "SELECT * FROM events WHERE kind = ? ORDER BY id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                out.append(
                    {
                        "id": row["id"],
                        "ts": row["ts"],
                        "kind": row["kind"],
                        "content": row["content"],
                        "meta": json.loads(row["meta"] or "{}"),
                        "prev_hash": row["prev_hash"],
                        "hash": row["hash"],
                    }
                )
        return out

    def last_of_kind(self, kind: str) -> Optional[Dict[str, Any]]:
        """Return the most recent event of a given kind."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE kind = ? ORDER BY id DESC LIMIT 1",
                (kind,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "ts": row["ts"],
                "kind": row["kind"],
                "content": row["content"],
                "meta": json.loads(row["meta"] or "{}"),
                "prev_hash": row["prev_hash"],
                "hash": row["hash"],
            }

    def read_up_to(self, event_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE id <= ? ORDER BY id ASC",
                (event_id,),
            )
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for row in rows:
                out.append(
                    {
                        "id": row["id"],
                        "ts": row["ts"],
                        "kind": row["kind"],
                        "content": row["content"],
                        "meta": json.loads(row["meta"] or "{}"),
                        "prev_hash": row["prev_hash"],
                        "hash": row["hash"],
                    }
                )
        return out

    # Convenience API for validators/replay
    def get(self, event_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "ts": row["ts"],
                "kind": row["kind"],
                "content": row["content"],
                "meta": json.loads(row["meta"] or "{}"),
                "prev_hash": row["prev_hash"],
                "hash": row["hash"],
            }

    def exists(self, event_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,))
            return cur.fetchone() is not None

    def hash_sequence(self) -> List[str]:
        with self._lock:
            cur = self._conn.execute("SELECT hash FROM events ORDER BY id ASC")
            return [r[0] for r in cur.fetchall()]

    def count(self) -> int:
        """Return total event count using MAX(id) (append-only, no deletes)."""
        with self._lock:
            cur = self._conn.execute("SELECT MAX(id) FROM events")
            row = cur.fetchone()
            max_id = row[0] if row and row[0] is not None else 0
            return int(max_id)

    def has_exec_bind(self, cid: str) -> bool:
        cid = (cid or "").strip()
        if not cid:
            return False
        events = self.read_all()
        for event in events:
            if event.get("kind") != "config":
                continue
            content_raw = event.get("content") or ""
            try:
                data = json.loads(content_raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") == "exec_bind" and data.get("cid") == cid:
                return True
        return False
