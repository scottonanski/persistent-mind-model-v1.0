# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Deterministic lifetime memory chunks for long-range recall.

Creates compact, searchable `lifetime_memory` events that summarize
older spans of the ledger. This enables hierarchical retrieval:
- recent window stays fast
- older spans remain discoverable via vector search over memory chunks
- evidence samples from the span are linked via sample_ids
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog
from pmm.retrieval.vector import ensure_embedding_for_event


DEFAULT_CHUNK_EVENTS = 120
DEFAULT_MESSAGE_SAMPLES = 32


def _truncate(text: str, limit: int = 240) -> str:
    text = (text or "").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _sample_messages(events: List[Dict], max_samples: int) -> List[Dict]:
    msgs = [e for e in events if e.get("kind") in ("user_message", "assistant_message")]
    if not msgs:
        return []
    max_samples = max(1, int(max_samples))
    stride = max(1, len(msgs) // max_samples)
    sampled: List[Dict] = []
    for idx in range(0, len(msgs), stride):
        sampled.append(msgs[idx])
        if len(sampled) == max_samples:
            break
    return sampled


def maybe_append_lifetime_memory(
    eventlog: EventLog,
    concept_graph: ConceptGraph,
    *,
    chunk_size: int = DEFAULT_CHUNK_EVENTS,
    message_samples: int = DEFAULT_MESSAGE_SAMPLES,
) -> Optional[int]:
    """Append a lifetime_memory event once the chunk threshold is met.

    Chunking is progressive: each lifetime_memory event records the
    highest ledger id it covered. Subsequent calls resume from that id.
    """
    last_chunk = eventlog.last_of_kind("lifetime_memory")
    start_after = 0
    if last_chunk:
        meta = last_chunk.get("meta") or {}
        try:
            start_after = int(meta.get("covered_until", last_chunk["id"]))
        except Exception:
            start_after = int(last_chunk["id"])

    # Fetch a buffer beyond the target size to account for filtered kinds.
    buffer_multiplier = 2
    candidates = eventlog.read_since(start_after, limit=chunk_size * buffer_multiplier)
    # Exclude previously synthesized lifetime_memory events from the span.
    span_events = [e for e in candidates if e.get("kind") != "lifetime_memory"]

    if len(span_events) < chunk_size:
        return None

    span = span_events[:chunk_size]
    span_start = int(span[0]["id"])
    span_end = int(span[-1]["id"])

    sampled_msgs = _sample_messages(span, message_samples)
    sample_ids = [int(e["id"]) for e in sampled_msgs]

    # Collect frequently bound concepts within the span.
    concept_counts: Dict[str, int] = {}
    for ev in span:
        for tok in concept_graph.concepts_for_event(int(ev["id"])):
            concept_counts[tok] = concept_counts.get(tok, 0) + 1
    top_concepts = sorted(concept_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    top_tokens = [t for t, _c in top_concepts]

    # Capture commitment openings/closures for continuity.
    opened: List[str] = []
    closed: List[str] = []
    for ev in span:
        meta = ev.get("meta") or {}
        if ev.get("kind") == "commitment_open":
            cid = meta.get("cid") or ""
            text = meta.get("text") or ev.get("content") or ""
            opened.append(f"{cid}:{_truncate(text, 120)}")
        elif ev.get("kind") == "commitment_close":
            cid = meta.get("cid") or ""
            closed.append(cid)

    lines: List[str] = [
        f"Span {span_start}..{span_end} ({len(span)} events)",
    ]
    if top_tokens:
        lines.append(f"Concepts: {', '.join(top_tokens)}")
    if opened:
        lines.append(f"Commitments opened: {', '.join(opened[:8])}")
    if closed:
        lines.append(f"Commitments closed: {', '.join(sorted(set(closed))[:8])}")
    if sampled_msgs:
        lines.append("Messages:")
        for msg in sampled_msgs:
            role = (msg.get("meta") or {}).get("role") or msg.get("kind")
            content = _truncate(msg.get("content") or "")
            lines.append(f"- [{msg['id']}] {role}: {content}")

    content = "\n".join(lines)
    meta = {
        "span_start": span_start,
        "span_end": span_end,
        "covered_until": span_end,
        "sample_ids": sample_ids,
        "concepts": top_tokens,
        "summary_kind": "lifetime_memory",
    }

    eid = eventlog.append(
        kind="lifetime_memory",
        content=content,
        meta=meta,
    )

    # Precompute embedding for summary chunks to keep vector search fast.
    ensure_embedding_for_event(
        events=span,
        eventlog=eventlog,
        event_id=eid,
        text=content,
        model="hash64",
        dims=64,
    )

    return eid
