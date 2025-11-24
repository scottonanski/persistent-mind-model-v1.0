# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

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
        with self._lock:
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
            # New kinds for Indexer/Archivist
            "claim_from_text",
            "concept_bind_async",
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
                        # Write violation directly
                        with self._lock, self._conn:
                            v_payload = {
                                "kind": "violation",
                                "content": v_content,
                                "meta": v_meta,
                                "prev_hash": prev_hash,
                            }
                            v_digest = sha256(
                                _canonical_json(v_payload).encode("utf-8")
                            ).hexdigest()
                            curv = self._conn.execute(
                                "INSERT INTO events (ts, kind, content, meta, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?)",
                                (
                                    ts,
                                    "violation",
                                    v_content,
                                    _canonical_json(v_meta),
                                    prev_hash,
                                    v_digest,
                                ),
                            )
                            v_id = int(curv.lastrowid)
                            self._emit(
                                {
                                    "id": v_id,
                                    "ts": ts,
                                    "kind": "violation",
                                    "content": v_content,
                                    "meta": v_meta,
                                    "prev_hash": prev_hash,
                                    "hash": v_digest,
                                }
                            )
                        raise PermissionError(f"Policy forbids {src} writing {kind}")
            except PermissionError:
                raise
            except Exception:
                # Fail-open if policy unreadable
                pass

        with self._lock, self._conn:
            # Idempotent append using UNIQUE(hash) and INSERT OR IGNORE:
            # - On first insert, a new row is created.
            # - On conflict, no new row is created; we look up the existing row
            #   and emit it to listeners, returning its id.
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO events (ts, kind, content, meta, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?)",
                (ts, kind, content, _canonical_json(meta), prev_hash, digest),
            )
            if cur.rowcount == 0:
                # Row with identical hash already exists; fetch canonical row.
                cur_row = self._conn.execute(
                    "SELECT id, ts, kind, content, meta, prev_hash, hash FROM events WHERE hash = ?",
                    (digest,),
                )
                row = cur_row.fetchone()
                if row is None:
                    raise RuntimeError("Invariant violation: hash conflict without row")
                ev_id = int(row["id"])
                ts_db = row["ts"]
                kind_db = row["kind"]
                content_db = row["content"]
                meta_db = json.loads(row["meta"] or "{}")
                prev_hash_db = row["prev_hash"]
                hash_db = row["hash"]
            else:
                ev_id = int(cur.lastrowid)
                ts_db = ts
                kind_db = kind
                content_db = content
                meta_db = meta
                prev_hash_db = prev_hash
                hash_db = digest

        ev = {
            "id": ev_id,
            "ts": ts_db,
            "kind": kind_db,
            "content": content_db,
            "meta": meta_db,
            "prev_hash": prev_hash_db,
            "hash": hash_db,
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
