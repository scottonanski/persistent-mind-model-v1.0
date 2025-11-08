# Path: pmm/core/event_log.py
"""SQLite-backed EventLog with simple hash-chain integrity.

Minimal deterministic append/query API for PMM.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Dict, List, Optional


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class EventLog:
    """Persistent append-only log of events with hash chaining."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._listeners: List = []
        self._init_db()

    def _init_db(self) -> None:
        with self._conn:
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

    def register_listener(self, callback) -> None:
        """Register a callback(event_dict) when an event is appended."""
        with self._lock:
            self._listeners.append(callback)

    def _emit(self, ev: Dict[str, Any]) -> None:
        for cb in list(self._listeners):
            try:
                cb(ev)
            except Exception:
                # Listeners should not break the log
                pass

    def _last_hash(self) -> Optional[str]:
        cur = self._conn.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return row[0] if row and row[0] else None

    def append(
        self, *, kind: str, content: str, meta: Optional[Dict[str, Any]] = None
    ) -> int:
        valid_kinds = {
            "user_message",
            "assistant_message",
            "reflection",
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
        ts = _iso_now()
        prev_hash = self._last_hash()
        # Hash payload intentionally excludes timestamp to keep digest
        # stable across independent runs producing identical semantic content.
        payload = {
            "kind": kind,
            "content": content,
            "meta": meta,
            "prev_hash": prev_hash,
        }
        digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

        # Soft idempotency guard: if the computed digest equals the last
        # row's hash, return the existing last id instead of inserting a
        # duplicate row. This preserves replay determinism without a DB
        # UNIQUE constraint and avoids accidental duplicate writes.
        with self._lock:
            cur_last = self._conn.execute(
                "SELECT id, hash FROM events ORDER BY id DESC LIMIT 1"
            )
            last_row = cur_last.fetchone()
            if last_row is not None:
                last_id, last_hash = int(last_row[0]), last_row[1]
                if last_hash == digest:
                    # Emit to listeners to preserve live projections, since
                    # downstream code may rely on the callback side‑effects
                    # during append paths. Listeners should be idempotent.
                    ev = {
                        "id": last_id,
                        "ts": "",  # unknown here; listeners should not rely on ts
                        "kind": kind,
                        "content": content,
                        "meta": meta,
                        "prev_hash": prev_hash,
                        "hash": digest,
                    }
                    self._emit(ev)
                    return last_id

        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO events (ts, kind, content, meta, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?)",
                (ts, kind, content, _canonical_json(meta), prev_hash, digest),
            )
            ev_id = int(cur.lastrowid)

        ev = {
            "id": ev_id,
            "ts": ts,
            "kind": kind,
            "content": content,
            "meta": meta,
            "prev_hash": prev_hash,
            "hash": digest,
        }
        self._emit(ev)
        return ev_id

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

    def read_up_to(self, event_id: int) -> List[Dict[str, Any]]:
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
        cur = self._conn.execute("SELECT 1 FROM events WHERE id = ?", (event_id,))
        return cur.fetchone() is not None

    def hash_sequence(self) -> List[str]:
        cur = self._conn.execute("SELECT hash FROM events ORDER BY id ASC")
        return [r[0] for r in cur.fetchall()]

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
