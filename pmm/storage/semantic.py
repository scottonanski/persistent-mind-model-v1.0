from __future__ import annotations

import math
import sqlite3
from typing import Iterable, List, Optional, Sequence, Tuple


def _from_float32_le_blob(blob: bytes) -> List[float]:
    import struct

    if not blob:
        return []
    n = len(blob) // 4
    return list(struct.unpack("<" + "f" * n, blob))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def search_semantic(
    db: sqlite3.Connection,
    query_vec: Sequence[float],
    k: int = 5,
    scope_eids: Optional[Iterable[int]] = None,
) -> List[int]:
    """
    Brute-force cosine search over entries in event_embeddings.

    - Returns top-k eids by similarity.
    - If the side table is unavailable or empty, returns [].
    - scope_eids can restrict the search to a subset of eids.
    """
    # Check for table existence first
    cur = db.cursor()
    cur.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='event_embeddings'
        """
    )
    if not cur.fetchone():
        return []

    if scope_eids:
        scope = list(scope_eids)
        if not scope:
            return []
        placeholders = ",".join(["?"] * len(scope))
        cur = db.execute(
            f"SELECT eid, embedding FROM event_embeddings WHERE eid IN ({placeholders})",
            tuple(int(x) for x in scope),
        )
    else:
        cur = db.execute("SELECT eid, embedding FROM event_embeddings")

    q = list(float(x) for x in query_vec)
    scored: List[Tuple[float, int]] = []
    rows = cur.fetchall()
    if not rows:
        return []
    for row in rows:
        # Support both tuple and sqlite3.Row
        eid = int(row[0]) if isinstance(row, tuple) else int(row["eid"])  # type: ignore[index]
        blob = row[1] if isinstance(row, tuple) else row["embedding"]  # type: ignore[index]
        vec = _from_float32_le_blob(blob)
        sim = _cosine(q, vec)
        scored.append((sim, eid))

    scored.sort(key=lambda t: t[0], reverse=True)
    if k <= 0:
        return []
    return [eid for _, eid in scored[:k]]
