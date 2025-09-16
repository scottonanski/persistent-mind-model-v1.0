from __future__ import annotations

from typing import Dict, List, Tuple

import struct as _struct

from pmm.storage.eventlog import EventLog
from pmm.runtime.embeddings import (
    compute_embedding as _emb_compute,
    digest_vector as _emb_digest,
)


def _response_events(events: List[Dict]) -> List[Tuple[int, str]]:
    out: List[Tuple[int, str]] = []
    for ev in events:
        if ev.get("kind") == "response":
            try:
                eid = int(ev.get("id") or 0)
            except Exception:
                eid = 0
            if eid <= 0:
                continue
            out.append((eid, str(ev.get("content") or "")))
    return out


def _processed_eids(events: List[Dict]) -> set[int]:
    """Return eids that have been indexed already.

    Only "embedding_indexed" counts as processed. "embedding_skipped" does NOT
    mark an eid as processed so that re-runs without a provider can continue to
    emit deterministic skip markers each pass (used by tests).
    """
    have: set[int] = set()
    for ev in events:
        k = ev.get("kind")
        if k not in ("embedding_indexed",):
            continue
        try:
            eid = int((ev.get("meta") or {}).get("eid"))
            have.add(eid)
        except Exception:
            continue
    return have


def find_missing_response_eids(eventlog: EventLog) -> List[int]:
    """Return response event ids that have no corresponding embedding_indexed event.

    Deterministic: uses a single read_all pass and returns ids in ascending order.
    """
    events = eventlog.read_all()
    resp = _response_events(events)
    have = _processed_eids(events)
    missing = [eid for (eid, _text) in resp if eid not in have]
    missing.sort()
    return missing


def process_backlog(
    eventlog: EventLog, *, batch_limit: int | None = None, use_real: bool = False
) -> Dict:
    """Catch up on missing embeddings for response events.

    For each missing response eid:
      - compute embedding via runtime.embeddings
      - append embedding_indexed with digest if successful; also write side-table row when available
      - on failure or if embedding None, append embedding_skipped and continue

    Returns a summary dict with counts.
    """
    missing = find_missing_response_eids(eventlog)
    if batch_limit is not None:
        missing = missing[: max(0, int(batch_limit))]
    counts = {"indexed": 0, "skipped": 0, "processed": 0}
    # Build a map from id to content for deterministic lookup
    content_by_id: Dict[int, str] = {}
    for eid, text in _response_events(eventlog.read_all()):
        content_by_id[int(eid)] = str(text or "")
    for eid in missing:
        text = content_by_id.get(int(eid), "")
        try:
            vec = _emb_compute(text)
        except Exception:
            vec = None
        if vec is None:
            # Deterministic always-on path should rarely hit this; treat as processed without ledger noise
            counts["processed"] += 1
            continue
        # Append embedding_indexed and attempt to persist in side table if available
        try:
            digest = _emb_digest(vec)
            eventlog.append(
                kind="embedding_indexed",
                content="",
                meta={"eid": int(eid), "digest": digest},
            )
            counts["indexed"] += 1
            # Side-table persistence (optional)
            try:
                if (
                    getattr(eventlog, "has_embeddings_index", False)
                    and eventlog.has_embeddings_index
                ):
                    blob = _struct.pack("<" + "f" * len(vec), *[float(x) for x in vec])
                    eventlog.insert_embedding_row(
                        eid=int(eid), digest=str(digest), embedding_blob=blob
                    )
            except Exception:
                # Never allow side-table errors to bubble up
                pass
        except Exception:
            # Ignore individual failures to keep backlog resilient
            pass
        counts["processed"] += 1
    return counts
