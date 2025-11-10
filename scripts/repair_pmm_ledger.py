#!/usr/bin/env python3
"""Deterministic ledger repair utility for Persistent Mind Model.

This tool rebuilds a fresh SQLite ledger by correcting malformed CLOSE tokens
and recomputing the hash chain exactly as `EventLog.append` does.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

TARGET_EVENT_IDS = {170, 414, 443, 499, 970}


@dataclass
class EventRow:
    """In-memory representation of a ledger row."""

    id: int
    ts: str
    kind: str
    content: str
    meta_text: str
    prev_hash: Optional[str]
    hash: Optional[str]


def canonical_json(obj: Dict) -> str:
    """Serialize using the exact canonical form from EventLog."""

    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def make_cid(title: str) -> str:
    """Derive the canonical commitment ID (first 8 hex of SHA-1)."""

    normalized = (title or "").strip()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    return digest[:8]


def extract_commit_title(content: str) -> str:
    """Find the first COMMIT line and return its title segment."""

    for line in content.splitlines():
        stripped = line.strip()
        if "COMMIT:" not in stripped:
            continue
        after = stripped.split("COMMIT:", 1)[1]
        title_segment = after.split("|")[0]
        title = title_segment.strip()
        if title:
            return title
    raise ValueError("COMMIT line not found when deriving CID")


def replace_close_token(content: str, cid: str) -> str:
    """Replace the first CLOSE token with the provided CID."""

    pattern = re.compile(r"(CLOSE:\s*)([^|\n\r]+)")

    def _replacer(match: re.Match[str]) -> str:
        return f"{match.group(1)}{cid}"

    new_content, count = pattern.subn(_replacer, content, count=1)
    if count == 0:
        raise ValueError("CLOSE marker not found for repair")
    return new_content


def load_events(path: Path) -> List[EventRow]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    events: List[EventRow] = []
    try:
        with conn:
            for row in conn.execute("SELECT * FROM events ORDER BY id ASC"):
                events.append(
                    EventRow(
                        id=int(row["id"]),
                        ts=row["ts"],
                        kind=row["kind"],
                        content=row["content"],
                        meta_text=row["meta"],
                        prev_hash=row["prev_hash"],
                        hash=row["hash"],
                    )
                )
    finally:
        conn.close()
    return events


def repair_content(events: Sequence[EventRow]) -> List[EventRow]:
    repaired: List[EventRow] = []
    for event in events:
        if event.id in TARGET_EVENT_IDS and event.kind == "assistant_message":
            title = extract_commit_title(event.content)
            cid = make_cid(title)
            updated_content = replace_close_token(event.content, cid)
            repaired.append(
                EventRow(
                    id=event.id,
                    ts=event.ts,
                    kind=event.kind,
                    content=updated_content,
                    meta_text=event.meta_text,
                    prev_hash=event.prev_hash,
                    hash=event.hash,
                )
            )
        else:
            repaired.append(event)
    return repaired


def rebuild_database(events: Sequence[EventRow], dest: Path) -> None:
    conn = sqlite3.connect(dest)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE events (
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
            prev_hash: Optional[str] = None
            for event in events:
                meta_dict = json.loads(event.meta_text or "{}")
                payload = {
                    "kind": event.kind,
                    "content": event.content,
                    "meta": meta_dict,
                    "prev_hash": prev_hash,
                }
                digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
                conn.execute(
                    """
                    INSERT INTO events (id, ts, kind, content, meta, prev_hash, hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.ts,
                        event.kind,
                        event.content,
                        event.meta_text,
                        prev_hash,
                        digest,
                    ),
                )
                prev_hash = digest
    finally:
        conn.close()


def verify_chain(conn: sqlite3.Connection) -> bool:
    conn.row_factory = sqlite3.Row
    prev_hash: Optional[str] = None
    for row in conn.execute("SELECT id, prev_hash, hash FROM events ORDER BY id ASC"):
        if row["prev_hash"] != prev_hash:
            return False
        prev_hash = row["hash"]
    return True


def audit_close_tokens(conn: sqlite3.Connection) -> List[int]:
    conn.row_factory = sqlite3.Row
    bad_ids: List[int] = []
    token_pattern = re.compile(r"CLOSE:\s*([0-9a-f]{8})")
    for row in conn.execute(
        "SELECT id, content FROM events WHERE kind='assistant_message' AND content LIKE '%CLOSE:%'"
    ):
        content = row["content"]
        valid = True
        for line in content.splitlines():
            if "CLOSE:" not in line:
                continue
            match = token_pattern.search(line)
            if not match:
                valid = False
                break
        if not valid:
            bad_ids.append(int(row["id"]))
    return bad_ids


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(".data/pmmdb/pmm.db"),
        help="Path to the existing ledger database.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path(".data/pmmdb/pmm_fixed.db"),
        help="Destination path for the rebuilt ledger.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite destination if it already exists.",
    )

    args = parser.parse_args(argv)
    source = args.source.resolve()
    dest = args.dest.resolve()

    if not source.exists():
        raise SystemExit(f"Source database not found: {source}")
    if dest.exists() and not args.force:
        raise SystemExit(
            f"Destination already exists: {dest}. Remove it first or pass --force."
        )
    if dest.exists():
        dest.unlink()

    original_events = load_events(source)
    repaired_events = repair_content(original_events)

    rebuild_database(repaired_events, dest)

    with sqlite3.connect(dest) as conn:
        total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        chain_ok = verify_chain(conn)
        bad_close_ids = audit_close_tokens(conn)

    repaired_ids = sorted(
        event.id
        for event, original in zip(repaired_events, original_events)
        if event.content != original.content
    )

    summary = {
        "total_events": total_events,
        "repaired_events": repaired_ids,
        "chain_continuity": chain_ok,
        "close_token_audit": "clean" if not bad_close_ids else bad_close_ids,
        "dest_path": str(dest),
    }

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
