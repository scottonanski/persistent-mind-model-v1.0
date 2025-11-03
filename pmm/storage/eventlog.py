"""Minimal SQLite-backed event log.

Intent:
- Provide a tiny, reliable event store with two primary operations:
  `append(...)` and `read_all()`.
- Hash chaining is implemented via prev_hash/hash columns for integrity.

Schema (created if absent):
- Table `events` with columns:
  - id INTEGER PRIMARY KEY AUTOINCREMENT
  - ts TEXT NOT NULL  (ISO8601 UTC with trailing 'Z')
  - kind TEXT NOT NULL
  - content TEXT NOT NULL
  - meta TEXT NOT NULL  (JSON-encoded dict)

Notes:
- Uses sqlite3 with `check_same_thread=False` to allow basic cross-thread usage.
- Optionally enables WAL/journal and synchronous pragmas for durability without
  complicating this initial scaffolding.
"""

from __future__ import annotations

import datetime as _dt
import hashlib as _hashlib
import json as _json
import os as _os
import sqlite3 as _sqlite3
from collections.abc import Callable
from threading import RLock
from typing import Any


class EventLog:
    """SQLite event log with minimal API.

    Parameters
    ----------
    path : str
        Filesystem path to the SQLite database. Parent directories are created
        if they do not exist. Default is `.data/pmm.db` relative to CWD.
    """

    def __init__(self, path: str = ".data/pmm.db") -> None:
        self.path = path
        self._lock = RLock()
        self._events_cache: list[dict[str, Any]] | None = None
        self._cache_last_id: int = 0
        self._append_listeners: list[Callable[[dict[str, Any]], None]] = []

        # Ensure parent directory exists
        parent = _os.path.dirname(_os.path.abspath(self.path))
        if parent and not _os.path.exists(parent):
            _os.makedirs(parent, exist_ok=True)

        # Create connection and initialize schema
        self._conn = _sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._create_tables()
        # Opportunistically create embeddings side table (feature-detected capability)
        try:
            self._embeddings_index_available = self._ensure_embeddings_side_table()
        except Exception:
            self._embeddings_index_available = False

        # Optional, lazily-initialized side-table for large blobs. We never
        # mutate existing events; blobs are auxiliary storage for read-time
        # hydration only.
        self._blobs_table_ready: bool | None = None

    # ------------------------------------------------------------------
    # Cache coordination helpers
    # ------------------------------------------------------------------

    def get_max_id(self) -> int:
        """Return the largest event ID currently persisted."""
        with self._lock:
            return self._get_max_id_unlocked()

    def _get_max_id_unlocked(self) -> int:
        cur = self._conn.execute("SELECT MAX(id) FROM events")
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _refresh_cache_locked(self) -> None:
        """Synchronize the in-memory cache with the backing database."""

        max_id = self._get_max_id_unlocked()

        # Cache already mirrors the ledger tail.
        if self._events_cache is not None and self._cache_last_id == max_id:
            return

        if max_id == 0:
            self._events_cache = []
            self._cache_last_id = 0
            return

        if self._events_cache is None or self._cache_last_id == 0:
            # Cold start: rebuild cache from scratch.
            cur = self._conn.execute(
                "SELECT id, ts, kind, content, meta FROM events ORDER BY id ASC"
            )
            rows = cur.fetchall()
            cache: list[dict] = []
            for rid, ts, kind, content, meta_json in rows:
                try:
                    meta_obj = _json.loads(meta_json) if meta_json else {}
                except Exception:
                    meta_obj = {}
                cache.append(
                    {
                        "id": int(rid),
                        "ts": str(ts),
                        "kind": str(kind),
                        "content": str(content),
                        "meta": meta_obj,
                    }
                )
            self._events_cache = cache
            self._cache_last_id = max_id
            return

        # Incremental refresh: append rows beyond the cached tail.
        cur = self._conn.execute(
            "SELECT id, ts, kind, content, meta FROM events WHERE id > ? ORDER BY id ASC",
            (self._cache_last_id,),
        )
        rows = cur.fetchall()

        if not rows:
            # Defensive rebuild if cache diverged (should be rare).
            self._events_cache = None
            self._cache_last_id = 0
            self._refresh_cache_locked()
            return

        for rid, ts, kind, content, meta_json in rows:
            try:
                meta_obj = _json.loads(meta_json) if meta_json else {}
            except Exception:
                meta_obj = {}
            self._events_cache.append(
                {
                    "id": int(rid),
                    "ts": str(ts),
                    "kind": str(kind),
                    "content": str(content),
                    "meta": meta_obj,
                }
            )

        self._cache_last_id = max_id

    def _create_tables(self) -> None:
        with self._lock:
            with self._conn:  # implicit transaction
                self._conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        content TEXT NOT NULL,
                        meta TEXT NOT NULL
                    );
                    """
                )
                # Helpful indexes for typical queries
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);"
                )
                # Composite indexes for performance (Phase 1.2 optimization)
                # Used by: read_after_id with kind filtering, metrics queries
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_kind_id ON events(kind, id);"
                )
                # Used by: read_after_ts queries, temporal filtering
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_ts_id ON events(ts, id);"
                )
                # Partial index for fast metrics lookup (most recent metrics_update)
                self._conn.execute(
                    """CREATE INDEX IF NOT EXISTS idx_metrics_lookup
                       ON events(id DESC) WHERE kind='metrics_update';"""
                )
                # Ensure hash-chain columns exist (idempotent migration)
                cols = self._get_columns()
                if "prev_hash" not in cols:
                    # Nullable for genesis only
                    self._conn.execute("ALTER TABLE events ADD COLUMN prev_hash TEXT")
                if "hash" not in cols:
                    # Store SHA-256 hex digest; allow NULL temporarily for migration, but appends always set it
                    self._conn.execute("ALTER TABLE events ADD COLUMN hash TEXT")

    # --------- Embeddings Side Table (optional, feature-detected) ----------
    def _ensure_embeddings_side_table(self) -> bool:
        """Create side table for semantic embeddings if not exists. Returns True on success.

        Never raises; returns False to keep runtime resilient.
        """
        try:
            with self._lock:
                with self._conn:
                    self._conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS event_embeddings (
                            eid INTEGER PRIMARY KEY,
                            digest TEXT,
                            embedding BLOB,
                            summary TEXT,
                            keywords TEXT,
                            created_at INTEGER
                        );
                        """
                    )
            return True
        except Exception:
            return False

    @property
    def has_embeddings_index(self) -> bool:
        return bool(getattr(self, "_embeddings_index_available", False))

    def insert_embedding_row(
        self,
        *,
        eid: int,
        digest: str | None,
        embedding_blob: bytes | None,
        summary: str | None = None,
        keywords: str | None = None,
        created_at: int | None = None,
    ) -> bool:
        """Insert a row into event_embeddings. No-op if side table unavailable.

        Returns True if a row was written, False otherwise.
        """
        if not self.has_embeddings_index:
            return False
        try:
            import time as _time

            ts = int(_time.time()) if created_at is None else int(created_at)
            with self._lock:
                with self._conn:
                    self._conn.execute(
                        """
                        INSERT OR REPLACE INTO event_embeddings
                            (eid, digest, embedding, summary, keywords, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (int(eid), digest, embedding_blob, summary, keywords, ts),
                    )
            return True
        except Exception:
            return False

    def _get_columns(self) -> list[str]:
        cur = self._conn.execute("PRAGMA table_info('events')")
        return [str(row[1]) for row in cur.fetchall()]

    def _get_last_hash(self) -> str | None:
        with self._lock:
            cur = self._conn.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if not row:
                return None
            h = row[0]
            return str(h) if h else None

    @staticmethod
    def _canonical_json(obj: dict) -> bytes:
        # Compact separators + sorted keys ensures deterministic hashing
        return _json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def append(self, kind: str, content: str, meta: dict | None = None) -> int:
        event_record: dict[str, Any] | None = None
        with self._lock:
            ts = _dt.datetime.now(_dt.timezone.utc).isoformat()
            meta_obj: dict = meta or {}
            meta_json = _json.dumps(meta_obj)
            prev = self._get_last_hash()
            with self._conn:
                cur = self._conn.execute(
                    "INSERT INTO events(ts, kind, content, meta, prev_hash) VALUES (?, ?, ?, ?, ?)",
                    (ts, kind, content, meta_json, prev),
                )
                eid = int(cur.lastrowid)
                payload = {
                    "id": eid,
                    "ts": ts,
                    "kind": kind,
                    "content": content,
                    "meta": meta_obj,
                    "prev_hash": prev,
                }
                digest = _hashlib.sha256(self._canonical_json(payload)).hexdigest()
                self._conn.execute("UPDATE events SET hash=? WHERE id=?", (digest, eid))
                event_record = {
                    "id": eid,
                    "ts": ts,
                    "kind": kind,
                    "content": content,
                    "meta": dict(meta_obj),
                }
                if self._events_cache is not None:
                    self._events_cache.append(event_record)
                    self._cache_last_id = eid
        if event_record is not None:
            for callback in list(self._append_listeners):
                try:
                    callback(event_record)
                except Exception:
                    continue
        return eid

    def read_all(self) -> list[dict]:
        with self._lock:
            self._refresh_cache_locked()
            if self._events_cache is not None:
                return self._events_cache[:]
            return []

    def get_latest_stage_event(self) -> dict[str, Any] | None:
        """Return the most recent stage_update or stage_progress event."""

        with self._lock:
            cur = self._conn.execute(
                """
                SELECT id, kind, content, meta
                  FROM events
                 WHERE kind IN ('stage_update', 'stage_progress')
                 ORDER BY id DESC
                 LIMIT 1
                """
            )
            row = cur.fetchone()
        if not row:
            return None
        eid, kind, content, meta_json = row
        try:
            meta = _json.loads(meta_json) if meta_json else {}
        except Exception:
            meta = {}
        return {
            "id": int(eid),
            "kind": str(kind),
            "content": str(content),
            "meta": meta,
        }

    def get_recent_reflections(self, limit: int = 2) -> list[dict[str, Any]]:
        """Return the most recent reflection events (default two)."""

        limit = max(int(limit), 1)
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT id, ts, content, meta
                  FROM events
                 WHERE kind = 'reflection'
                 ORDER BY id DESC
                 LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        result: list[dict[str, Any]] = []
        for eid, ts, content, meta_json in rows:
            try:
                meta = _json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            result.append(
                {
                    "id": int(eid),
                    "ts": str(ts) if ts is not None else "",
                    "content": str(content),
                    "meta": meta,
                }
            )
        return result

    def get_open_commitments(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return open commitments as [id, hash] pairs sorted descending."""

        sql = """
            WITH opens AS (
                SELECT id, hash, content, meta
                  FROM events
                 WHERE kind = 'commitment_open'
            ),
            closes AS (
                SELECT json_extract(meta, '$.open_id') AS open_id
                  FROM events
                 WHERE kind = 'commitment_close'
            )
            SELECT o.id, o.hash, o.content, o.meta
              FROM opens o
              LEFT JOIN closes c ON c.open_id = o.id
             WHERE c.open_id IS NULL
             ORDER BY o.id DESC
        """
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (max(int(limit), 1),)
        with self._lock:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall()
        result: list[dict[str, Any]] = []
        for eid, hval, content, meta_json in rows:
            try:
                meta = _json.loads(meta_json) if meta_json else {}
            except Exception:
                meta = {}
            result.append(
                {
                    "id": int(eid),
                    "hash": str(hval) if hval is not None else "",
                    "content": str(content),
                    "meta": meta,
                }
            )
        return result

    def get_ledger_head(self) -> dict[str, Any] | None:
        """Return the latest event id/hash/prev_hash."""

        with self._lock:
            cur = self._conn.execute(
                """
                SELECT id, hash, prev_hash
                  FROM events
                 ORDER BY id DESC
                 LIMIT 1
                """
            )
            row = cur.fetchone()
        if not row:
            return None
        eid, hval, prev = row
        return {
            "id": int(eid),
            "hash": str(hval) if hval is not None else "",
            "prev_hash": str(prev) if prev is not None else "",
        }

    def get_event_count(self) -> int:
        """Return the total number of events persisted."""

        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM events")
            row = cur.fetchone()
        if not row or row[0] is None:
            return 0
        return int(row[0])

    def read_after_id(self, *, after_id: int, limit: int) -> list[dict]:
        with self._lock:
            self._refresh_cache_locked()
            if self._events_cache is not None:
                result: list[dict] = []
                for ev in self._events_cache:
                    if int(ev.get("id") or 0) > int(after_id):
                        result.append(ev)
                        if len(result) >= int(limit):
                            break
                if result:
                    return result
            cur = self._conn.execute(
                "SELECT id, ts, kind, content, meta FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
                (int(after_id), int(limit)),
            )
            rows = cur.fetchall()
            result: list[dict] = []
            for rid, ts, kind, content, meta_json in rows:
                try:
                    meta_obj = _json.loads(meta_json) if meta_json else {}
                except Exception:
                    meta_obj = {}
                result.append(
                    {
                        "id": int(rid),
                        "ts": str(ts),
                        "kind": str(kind),
                        "content": str(content),
                        "meta": meta_obj,
                    }
                )
            return result

    def read_after_ts(self, *, after_ts: str, limit: int) -> list[dict]:
        with self._lock:
            self._refresh_cache_locked()
            if self._events_cache is not None:
                result: list[dict] = []
                for ev in self._events_cache:
                    if str(ev.get("ts")) > str(after_ts):
                        result.append(ev)
                        if len(result) >= int(limit):
                            break
                if result:
                    return result
            cur = self._conn.execute(
                "SELECT id, ts, kind, content, meta FROM events WHERE ts > ? ORDER BY id ASC LIMIT ?",
                (str(after_ts), int(limit)),
            )
            rows = cur.fetchall()
            result: list[dict] = []
            for rid, ts, kind, content, meta_json in rows:
                try:
                    meta_obj = _json.loads(meta_json) if meta_json else {}
                except Exception:
                    meta_obj = {}
                result.append(
                    {
                        "id": int(rid),
                        "ts": str(ts),
                        "kind": str(kind),
                        "content": str(content),
                        "meta": meta_obj,
                    }
                )
            return result

    def read_tail(self, *, limit: int) -> list[dict]:
        with self._lock:
            self._refresh_cache_locked()
            if self._events_cache:
                subset = self._events_cache[-int(limit) :]
                return list(subset)
            cur = self._conn.execute(
                "SELECT id, ts, kind, content, meta FROM events ORDER BY id DESC LIMIT ?",
                (int(limit),),
            )
            rows = cur.fetchall()
            rows.reverse()
            result: list[dict] = []
            for rid, ts, kind, content, meta_json in rows:
                try:
                    meta_obj = _json.loads(meta_json) if meta_json else {}
                except Exception:
                    meta_obj = {}
                result.append(
                    {
                        "id": int(rid),
                        "ts": str(ts),
                        "kind": str(kind),
                        "content": str(content),
                        "meta": meta_obj,
                    }
                )
            return result

    def read_by_ids(
        self, event_ids: list[int], *, verify_hash: bool = False
    ) -> list[dict]:
        """Read specific events by their IDs.

        Args:
            event_ids: List of event IDs to fetch
            verify_hash: If True, verify stored hash matches computed hash

        Returns:
            List of event dictionaries in same order as event_ids.
            Missing events are omitted from results.
        """
        if not event_ids:
            return []

        with self._lock:
            # Use parameterized query for efficiency
            placeholders = ",".join("?" * len(event_ids))
            cur = self._conn.execute(
                f"SELECT id, ts, kind, content, meta, hash FROM events WHERE id IN ({placeholders}) ORDER BY id ASC",
                event_ids,
            )
            rows = cur.fetchall()

            result: list[dict] = []
            for rid, ts, kind, content, meta_json, stored_hash in rows:
                try:
                    meta_obj = _json.loads(meta_json) if meta_json else {}
                except Exception:
                    meta_obj = {}

                event = {
                    "id": int(rid),
                    "ts": str(ts),
                    "kind": str(kind),
                    "content": str(content),
                    "meta": meta_obj,
                }

                # Optional hash verification
                if verify_hash and stored_hash:
                    payload = {
                        "id": int(rid),
                        "ts": str(ts),
                        "kind": str(kind),
                        "content": str(content),
                        "meta": meta_obj,
                        "prev_hash": None,  # Not needed for content verification
                    }
                    computed_hash = _hashlib.sha256(
                        self._canonical_json(payload)
                    ).hexdigest()
                    if computed_hash != stored_hash:
                        # Skip events with hash mismatches
                        continue

                result.append(event)

            return result

    def verify_chain(self) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, ts, kind, content, meta, prev_hash, hash FROM events ORDER BY id ASC"
            )
            rows = cur.fetchall()
            if not rows:
                return True
            prev_h = None
            for idx, (
                rid,
                ts,
                kind,
                content,
                meta_json,
                prev_hash,
                stored_hash,
            ) in enumerate(rows):
                # Genesis rule
                if idx == 0:
                    if prev_hash is not None:
                        return False
                else:
                    if prev_hash != prev_h:
                        return False

                try:
                    meta_obj = _json.loads(meta_json) if meta_json else {}
                except Exception:
                    meta_obj = {}

                payload = {
                    "id": int(rid),
                    "ts": str(ts),
                    "kind": str(kind),
                    "content": str(content),
                    "meta": meta_obj,
                    "prev_hash": prev_hash if prev_hash is not None else None,
                }
                recomputed = _hashlib.sha256(self._canonical_json(payload)).hexdigest()
                if stored_hash != recomputed:
                    return False
                prev_h = stored_hash
            return True

    def query(self, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """
        Query events from the log.

        Args:
            kind: Optional event type to filter by.
            limit: Maximum number of events to return.

        Returns:
            A list of event dictionaries with keys: id, timestamp, kind, content, meta.
        """
        with self._lock:
            if kind:
                cur = self._conn.execute(
                    "SELECT id, ts, kind, content, meta FROM events WHERE kind = ? ORDER BY id DESC LIMIT ?",
                    (kind, limit),
                )
            else:
                cur = self._conn.execute(
                    "SELECT id, ts, kind, content, meta FROM events ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            rows = cur.fetchall()
            result: list[dict[str, Any]] = []
            for rid, ts, event_kind, content, meta_json in rows:
                try:
                    meta_obj = _json.loads(meta_json) if meta_json else {}
                except Exception:
                    meta_obj = {}
                result.append(
                    {
                        "id": int(rid),
                        "timestamp": str(ts),
                        "kind": str(event_kind),
                        "content": str(content),
                        "meta": meta_obj,
                    }
                )
            return result

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        """
        Retrieve a specific event by its ID.

        Args:
            event_id: The ID of the event to retrieve.

        Returns:
            The event dictionary if found, None otherwise.
        """
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, ts, kind, content, meta, hash FROM events WHERE id = ?",
                (event_id,),
            )
            row = cur.fetchone()
            if row:
                try:
                    meta_obj = _json.loads(row[4]) if row[4] else {}
                except Exception:
                    meta_obj = {}
                return {
                    "id": int(row[0]),
                    "timestamp": str(row[1]),
                    "kind": str(row[2]),
                    "content": str(row[3]),
                    "meta": meta_obj,
                    "hash": str(row[5]) if row[5] else None,
                }
            return None

    def register_append_listener(
        self, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback invoked after each successful append."""
        with self._lock:
            self._append_listeners.append(callback)

    # ------------------------------------------------------------------
    # Tiered access helpers (bounded, deterministic; read-only)
    # ------------------------------------------------------------------

    def read_hot_events(self, *, limit: int = 2000) -> list[dict]:
        """Return recent events using a bounded tail window.

        Deterministic; equivalent to read_tail(limit=...). No writes.
        """
        lim = max(1, int(limit))
        return self.read_tail(limit=lim)

    def read_warm_events(
        self, *, since_id: int, until_id: int, limit: int = 10000
    ) -> list[dict]:
        """Return events in [since_id, until_id] inclusive, capped.

        - Ascending order by id
        - Cap limit to 10k to prevent unbounded reads
        - Read-only, deterministic
        """
        lo = max(0, int(since_id))
        hi = max(lo, int(until_id))
        lim = min(10000, max(1, int(limit)))
        with self._lock:
            cur = self._conn.execute(
                (
                    "SELECT id, ts, kind, content, meta FROM events "
                    "WHERE id >= ? AND id <= ? ORDER BY id ASC LIMIT ?"
                ),
                (lo, hi, lim),
            )
            rows = cur.fetchall()
        result: list[dict] = []
        for rid, ts, kind, content, meta_json in rows:
            try:
                meta_obj = _json.loads(meta_json) if meta_json else {}
            except Exception:
                meta_obj = {}
            result.append(
                {
                    "id": int(rid),
                    "ts": str(ts),
                    "kind": str(kind),
                    "content": str(content),
                    "meta": meta_obj,
                }
            )
        return result

    def read_cold_events(self, event_ids: list[int]) -> list[dict]:
        """Return specific events by ID via read_by_ids(). Read-only."""
        return self.read_by_ids(list(event_ids or []))

    # ------------------------------------------------------------------
    # Optional blob storage for large contents (no mutations to events)
    # ------------------------------------------------------------------

    def _ensure_event_blobs_table(self) -> bool:
        """Create side table for large event contents if not exists.

        Schema: event_blobs(eid INTEGER PRIMARY KEY, content BLOB, content_hash TEXT, created_at INTEGER)
        Returns True on success, False otherwise.
        """
        try:
            with self._lock:
                with self._conn:
                    self._conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS event_blobs (
                            eid INTEGER PRIMARY KEY,
                            content BLOB,
                            content_hash TEXT,
                            created_at INTEGER
                        );
                        """
                    )
            self._blobs_table_ready = True
            return True
        except Exception:
            self._blobs_table_ready = False
            return False

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return _hashlib.sha256(data).hexdigest()

    def insert_event_blob(self, *, eid: int, content: str) -> str | None:
        """Insert a blob row for the given event id.

        Does not alter the corresponding event row. Returns the content hash on
        success, None otherwise.
        """
        if not isinstance(eid, int) or eid <= 0:
            return None
        if not isinstance(content, str):
            return None
        if self._blobs_table_ready is None:
            self._ensure_event_blobs_table()
        if not self._blobs_table_ready:
            return None
        blob = content.encode("utf-8", errors="ignore")
        digest = self._sha256_bytes(blob)
        try:
            import time as _time

            with self._lock:
                with self._conn:
                    self._conn.execute(
                        """
                        INSERT OR REPLACE INTO event_blobs(eid, content, content_hash, created_at)
                        VALUES(?, ?, ?, ?)
                        """,
                        (int(eid), blob, digest, int(_time.time())),
                    )
            return digest
        except Exception:
            return None

    def _fetch_blob(self, blob_hash: str) -> bytes | None:
        """Fetch blob by content_hash. Returns bytes or None.

        Note: The table is keyed by eid; this helper searches by hash to keep it
        flexible for future lookups. Deterministic and read-only.
        """
        if not blob_hash:
            return None
        if self._blobs_table_ready is None:
            self._ensure_event_blobs_table()
        if not self._blobs_table_ready:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT content FROM event_blobs WHERE content_hash=? LIMIT 1",
                    (str(blob_hash),),
                ).fetchone()
            if not row:
                return None
            data = row[0]
            if isinstance(data, (bytes, bytearray)):
                return bytes(data)
            try:
                return bytes(data)
            except Exception:
                return None
        except Exception:
            return None

    def get_full_event(self, event_id: int) -> dict[str, Any] | None:
        """Return a single event, hydrating from blob store if referenced.

        Never mutates the underlying event. If a blob pointer is present in
        meta (e.g., meta['blob_hash'] or meta['content_hash']), attempts to
        fetch it and returns a copy with hydrated 'content'.
        """
        base = self.get_event(int(event_id))
        if not base:
            return None
        meta = base.get("meta") or {}
        blob_hash = meta.get("blob_hash") or meta.get("content_hash")
        if not blob_hash:
            return base
        data = self._fetch_blob(str(blob_hash))
        if data is None:
            return base
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = base.get("content", "")
        out = dict(base)
        out["content"] = text
        return out


def get_default_eventlog() -> EventLog:
    """Return the default eventlog instance."""
    from pmm.config import DEFAULT_DB_PATH

    env_path = _os.getenv("PMM_DB")
    if env_path:
        return EventLog(env_path)

    runtime_default = ".data/pmm.db"
    if DEFAULT_DB_PATH and DEFAULT_DB_PATH != runtime_default:
        default_path = DEFAULT_DB_PATH
        if _os.path.exists(default_path) and not _os.path.exists(runtime_default):
            return EventLog(default_path)

    return EventLog(runtime_default)
