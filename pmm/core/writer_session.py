"""Database-scoped writer ownership for the PMM canonical ledger."""

from __future__ import annotations

import os
import socket
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional


LEASE_SECONDS = 30.0
HEARTBEAT_SECONDS = 5.0
CLOCK_ROLLBACK_TOLERANCE_SECONDS = 1.0
_DB_NOW_SQL = "(julianday('now') - 2440587.5) * 86400.0"


class WriterOwnershipError(RuntimeError):
    """Base error for database-scoped writer ownership failures."""


class WriterOwnershipConflict(WriterOwnershipError):
    """Raised when another live owner already governs the database."""

    def __init__(
        self,
        *,
        owner_id: str,
        owner_role: str,
        lease_expires_at: float,
    ) -> None:
        self.owner_id = owner_id
        self.owner_role = owner_role
        self.lease_expires_at = lease_expires_at
        super().__init__(
            "database already has a live writer "
            f"owner={owner_id} role={owner_role} expires_at={lease_expires_at:.6f}"
        )


class WriterOwnershipBusy(WriterOwnershipError):
    """Raised when ownership cannot be inspected without hidden lock waiting."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"database writer reservation is busy; ownership not acquired: {path}"
        )


class WriterOwnershipLost(WriterOwnershipError):
    """Raised when a writer no longer owns the current fencing token."""


class WriterClockAnomaly(WriterOwnershipLost):
    """Raised when database wall time moves backwards beyond policy tolerance."""


@dataclass(frozen=True)
class WriterAuthority:
    database_uuid: str
    owner_id: str
    fence: int
    role: str


class WriterSession:
    """Exclusive fenced writer capability shared by same-owner services."""

    def __init__(
        self,
        *,
        path: str,
        role: str = "runtime",
        lease_seconds: float = LEASE_SECONDS,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if heartbeat_seconds <= 0 or heartbeat_seconds >= lease_seconds:
            raise ValueError(
                "heartbeat_seconds must be positive and below lease_seconds"
            )
        self.path = path
        self.role = role
        self.lease_seconds = float(lease_seconds)
        self.heartbeat_seconds = float(heartbeat_seconds)
        self.owner_id = uuid.uuid4().hex
        self.fence = 0
        self.database_uuid = ""
        self.operation_gate = threading.RLock()
        self._state_lock = threading.RLock()
        self._healthy = True
        self._lost_reason: Optional[str] = None
        self._stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    @property
    def authority(self) -> WriterAuthority:
        return WriterAuthority(
            database_uuid=self.database_uuid,
            owner_id=self.owner_id,
            fence=self.fence,
            role=self.role,
        )

    @property
    def healthy(self) -> bool:
        with self._state_lock:
            return self._healthy

    @property
    def lost_reason(self) -> Optional[str]:
        with self._state_lock:
            return self._lost_reason

    def mark_unhealthy(self, reason: str) -> None:
        with self._state_lock:
            if self._healthy:
                self._healthy = False
                self._lost_reason = reason

    def require_healthy(self) -> None:
        if not self.healthy:
            raise WriterOwnershipLost(self.lost_reason or "writer session is unhealthy")

    @contextmanager
    def operation(self) -> Iterator[None]:
        with self.operation_gate:
            self.require_healthy()
            yield

    def acquire_in_transaction(self, conn: sqlite3.Connection) -> None:
        now = float(conn.execute(f"SELECT {_DB_NOW_SQL}").fetchone()[0])
        identity = conn.execute(
            "SELECT database_uuid FROM pmm_database_identity WHERE singleton = 1"
        ).fetchone()
        if identity is None:
            self.database_uuid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO pmm_database_identity "
                "(singleton, database_uuid, control_schema_version) VALUES (1, ?, 1)",
                (self.database_uuid,),
            )
        else:
            self.database_uuid = str(identity[0])

        row = conn.execute(
            "SELECT owner_id, fence, lease_expires_at, owner_role, last_db_time "
            "FROM pmm_writer_lease WHERE singleton = 1"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO pmm_writer_lease "
                "(singleton, owner_id, fence, lease_expires_at, heartbeat_at, "
                "last_db_time, owner_pid, owner_host, owner_role) "
                "VALUES (1, NULL, 0, 0, NULL, ?, NULL, NULL, NULL)",
                (now,),
            )
            row = (None, 0, 0.0, None, now)

        current_owner = row[0]
        current_fence = int(row[1])
        expires_at = float(row[2] or 0.0)
        current_role = str(row[3] or "unknown")
        if current_owner is not None and now < expires_at:
            raise WriterOwnershipConflict(
                owner_id=str(current_owner),
                owner_role=current_role,
                lease_expires_at=expires_at,
            )

        self.fence = current_fence + 1
        lease_expires = 1.0e30 if self.path == ":memory:" else now + self.lease_seconds
        conn.execute(
            "UPDATE pmm_writer_lease SET owner_id = ?, fence = ?, "
            "lease_expires_at = ?, heartbeat_at = ?, last_db_time = ?, "
            "owner_pid = ?, owner_host = ?, owner_role = ? WHERE singleton = 1",
            (
                self.owner_id,
                self.fence,
                lease_expires,
                now,
                now,
                os.getpid(),
                socket.gethostname(),
                self.role,
            ),
        )

    def assert_authority_in_transaction(self, conn: sqlite3.Connection) -> float:
        self.require_healthy()
        now = float(conn.execute(f"SELECT {_DB_NOW_SQL}").fetchone()[0])
        row = conn.execute(
            "SELECT owner_id, fence, lease_expires_at, last_db_time "
            "FROM pmm_writer_lease WHERE singleton = 1"
        ).fetchone()
        if row is None:
            self.mark_unhealthy("writer lease row is missing")
            raise WriterOwnershipLost("writer lease row is missing")
        if now + CLOCK_ROLLBACK_TOLERANCE_SECONDS < float(row[3] or 0.0):
            self.mark_unhealthy("database clock moved backwards")
            raise WriterClockAnomaly("database clock moved backwards")
        if (
            row[0] != self.owner_id
            or int(row[1]) != self.fence
            or now >= float(row[2] or 0.0)
        ):
            self.mark_unhealthy("writer ownership or lease was lost")
            raise WriterOwnershipLost("writer ownership or lease was lost")
        return now

    def start_heartbeat(self) -> None:
        if self.path == ":memory:" or self._heartbeat_thread is not None:
            return
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"pmm-writer-heartbeat-{self.owner_id[:8]}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat_seconds):
            try:
                self._renew_once()
            except Exception as exc:  # health is surfaced through require_healthy
                self.mark_unhealthy(
                    f"heartbeat renewal failed: {type(exc).__name__}: {exc}"
                )
                return

    def _renew_once(self) -> None:
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=5.0)
        try:
            conn.execute("BEGIN IMMEDIATE")
            now = self.assert_authority_in_transaction(conn)
            conn.execute(
                "UPDATE pmm_writer_lease SET lease_expires_at = ?, heartbeat_at = ?, "
                "last_db_time = ? WHERE singleton = 1 AND owner_id = ? AND fence = ?",
                (
                    now + self.lease_seconds,
                    now,
                    now,
                    self.owner_id,
                    self.fence,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def release(self, conn: sqlite3.Connection) -> None:
        self._stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=max(1.0, self.heartbeat_seconds + 1.0))
        with self.operation_gate:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE pmm_writer_lease SET owner_id = NULL, lease_expires_at = 0, "
                    "heartbeat_at = NULL, owner_pid = NULL, owner_host = NULL, "
                    "owner_role = NULL WHERE singleton = 1 AND owner_id = ? AND fence = ?",
                    (self.owner_id, self.fence),
                )
                conn.commit()
            except sqlite3.Error:
                conn.rollback()
