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
import json as _json
import os as _os
import sqlite3 as _sqlite3
from typing import Dict, List
import hashlib as _hashlib


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

    def _create_tables(self) -> None:
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

    def _get_columns(self) -> List[str]:
        cur = self._conn.execute("PRAGMA table_info('events')")
        return [str(row[1]) for row in cur.fetchall()]

    def _get_last_hash(self) -> str | None:
        cur = self._conn.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return None
        h = row[0]
        return str(h) if h else None

    @staticmethod
    def _canonical_json(obj: Dict) -> bytes:
        # Compact separators + sorted keys ensures deterministic hashing
        return _json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def append(self, kind: str, content: str, meta: Dict | None = None) -> int:
        """Append an event and return its row id.

        Parameters
        ----------
        kind : str
            Event kind label (e.g., "prompt", "response", "reflection").
        content : str
            Raw string content associated with the event.
        meta : dict | None
            Optional metadata; will be JSON-serialized. Defaults to `{}`.
        """
        ts = _dt.datetime.now(_dt.UTC).isoformat()
        meta_obj: Dict = meta or {}
        meta_json = _json.dumps(meta_obj)
        prev = self._get_last_hash()
        with self._conn:
            # 1) Insert without hash to obtain id (store prev_hash now)
            cur = self._conn.execute(
                "INSERT INTO events(ts, kind, content, meta, prev_hash) VALUES (?, ?, ?, ?, ?)",
                (ts, kind, content, meta_json, prev),
            )
            eid = int(cur.lastrowid)
            # 2) Compute hash over normalized payload including id and prev_hash
            payload = {
                "id": eid,
                "ts": ts,
                "kind": kind,
                "content": content,
                "meta": meta_obj,
                "prev_hash": prev,
            }
            digest = _hashlib.sha256(self._canonical_json(payload)).hexdigest()
            # 3) Update row with hash
            self._conn.execute("UPDATE events SET hash=? WHERE id=?", (digest, eid))
            return eid

    def read_all(self) -> List[Dict]:
        """Read all events ordered by ascending id.

        Returns
        -------
        list[dict]
            Each event as {"id": int, "ts": str, "kind": str, "content": str, "meta": dict}.
        """
        cur = self._conn.execute(
            "SELECT id, ts, kind, content, meta FROM events ORDER BY id ASC"
        )
        rows = cur.fetchall()
        result: List[Dict] = []
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

    def read_after_id(self, *, after_id: int, limit: int) -> List[Dict]:
        """Return up to `limit` events where id > after_id, ordered by ascending id.

        Parameters
        ----------
        after_id : int
            Exclusive lower bound for the id.
        limit : int
            Maximum number of rows to return.
        """
        cur = self._conn.execute(
            "SELECT id, ts, kind, content, meta FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
            (int(after_id), int(limit)),
        )
        rows = cur.fetchall()
        result: List[Dict] = []
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

    def read_after_ts(self, *, after_ts: str, limit: int) -> List[Dict]:
        """Return up to `limit` events where ts > after_ts, ordered by ascending id.

        Parameters
        ----------
        after_ts : str
            ISO-8601 UTC timestamp string (exclusive lower bound on ts).
        limit : int
            Maximum number of rows to return.
        """
        cur = self._conn.execute(
            "SELECT id, ts, kind, content, meta FROM events WHERE ts > ? ORDER BY id ASC LIMIT ?",
            (str(after_ts), int(limit)),
        )
        rows = cur.fetchall()
        result: List[Dict] = []
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

    def read_tail(self, *, limit: int) -> List[Dict]:
        """Return the most recent <= limit events, ordered ascending by id.

        Parameters
        ----------
        limit : int
            Maximum number of rows to return.
        """
        cur = self._conn.execute(
            "SELECT id, ts, kind, content, meta FROM events ORDER BY id DESC LIMIT ?",
            (int(limit),),
        )
        rows = cur.fetchall()
        # rows are newest-first; reverse to ascending by id (newest last)
        rows.reverse()
        result: List[Dict] = []
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

    def verify_chain(self) -> bool:
        """Verify hash-chain integrity of the ledger.

        Rules:
        - Empty table is valid.
        - Genesis row must have prev_hash IS NULL.
        - Each row's prev_hash must equal the prior row's hash.
        - Each row's stored hash must match the recomputed digest over
          the canonical payload {id, ts, kind, content, meta, prev_hash}.
        """
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
