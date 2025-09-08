"""Minimal SQLite-backed event log.

Intent:
- Provide a tiny, reliable event store with two primary operations:
  `append(...)` and `read_all()`.
- This version does NOT implement hash chaining; it focuses on a stable base.

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

    def append(self, *, kind: str, content: str, meta: Dict | None = None) -> int:
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
        meta_json = _json.dumps(meta or {})
        with self._conn:  # implicit transaction
            cur = self._conn.execute(
                "INSERT INTO events(ts, kind, content, meta) VALUES (?, ?, ?, ?)",
                (ts, kind, content, meta_json),
            )
            return int(cur.lastrowid)

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

