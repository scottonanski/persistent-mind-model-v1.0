# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Deterministic, local vector selection for PMM (Phase 1).

No external calls. Embeddings are produced via a hashing-based projection
that is stable across runs and machines. Selection is based on cosine
similarity between the current query (user input) and candidate message
events from the ledger.
"""

from __future__ import annotations

from typing import Dict, List, Tuple
from hashlib import sha256
import math
import json

from pmm.core.event_log import EventLog
from pmm.core.mirror import Mirror
from pmm.runtime.context_utils import (
    render_graph_context,
    render_identity_claims,
    render_internal_goals,
    render_rsm,
)


class DeterministicEmbedder:
    def __init__(self, *, model: str = "hash64", dims: int = 64) -> None:
        self.model = model
        self.dims = max(8, int(dims))

    def _tok_vec(self, token: str) -> List[float]:
        """Return a deterministic pseudo-random vector for a token."""
        vec: List[float] = []
        # Produce dims 32-bit integers via sha256(token + ":" + i)
        for i in range(self.dims):
            h = sha256(f"{token}:{i}".encode("utf-8")).digest()
            # Take first 4 bytes -> uint32 -> map to [-1, 1]
            n = int.from_bytes(h[:4], byteorder="big", signed=False)
            x = (n / 2**32) * 2.0 - 1.0
            vec.append(x)
        return vec

    def embed(self, text: str) -> List[float]:
        toks = [t for t in (text or "").split() if t]
        if not toks:
            return [0.0] * self.dims
        agg = [0.0] * self.dims
        for t in toks:
            v = self._tok_vec(t)
            for i in range(self.dims):
                agg[i] += v[i]
        # L2 normalize
        norm = math.sqrt(sum(x * x for x in agg))
        if norm == 0.0:
            return [0.0] * self.dims
        return [x / norm for x in agg]


def cosine(a: List[float], b: List[float]) -> float:
    s = 0.0
    for i in range(min(len(a), len(b))):
        s += a[i] * b[i]
    return s


def candidate_messages(
    events: List[Dict], cap: int = 100, *, up_to_id: int | None = None
) -> List[Dict]:
    msgs = [
        e
        for e in events
        if e.get("kind") in ("user_message", "assistant_message")
        and (up_to_id is None or int(e.get("id", 0)) < int(up_to_id))
    ]
    # Keep the most recent `cap` messages
    return msgs[-cap:]


def select_by_vector(
    *,
    events: List[Dict],
    query_text: str,
    limit: int,
    model: str = "hash64",
    dims: int = 64,
    up_to_id: int | None = None,
) -> Tuple[List[int], List[float]]:
    """Return (selected_ids, scores) by cosine similarity to query.

    Deterministic, local-only scoring over recent candidate messages.
    """
    limit = max(1, int(limit))
    embedder = DeterministicEmbedder(model=model, dims=dims)
    q = embedder.embed(query_text)
    cands = candidate_messages(events, up_to_id=up_to_id)
    scored: List[Tuple[int, float]] = []
    for ev in cands:
        eid = int(ev.get("id", 0))
        text = ev.get("content") or ""
        v = embedder.embed(text)
        s = cosine(q, v)
        scored.append((eid, s))
    # Sort by score desc, tiebreak by id asc
    scored.sort(key=lambda t: (-t[1], t[0]))
    top = scored[:limit]
    ids = [eid for (eid, _s) in top]
    scores = [float(f"{_s:.6f}") for (_eid, _s) in top]
    return ids, scores


def build_context_from_ids(
    events: List[Dict], ids: List[int], *, eventlog: EventLog | None = None
) -> str:
    """Build context from selected event IDs with metadata blocks.

    Includes RSM, goals, and graph context when eventlog is provided,
    matching the behavior of fixed-window context building.
    """
    # Order chronologically for readability
    idset = set(ids)
    chosen = [e for e in events if int(e.get("id", 0)) in idset]
    chosen.sort(key=lambda e: int(e.get("id", 0)))
    lines: List[str] = []
    for e in chosen:
        kind = e.get("kind")
        content = e.get("content") or ""
        lines.append(f"{kind}: {content}")
    body = "\n".join(lines)

    # Add metadata blocks if eventlog provided
    if eventlog is None:
        return body

    mirror = Mirror(eventlog, enable_rsm=True, listen=False)
    snapshot = mirror.rsm_snapshot()
    identity_block = render_identity_claims(eventlog)
    rsm_block = render_rsm(snapshot)
    goals_block = render_internal_goals(eventlog)
    graph_block = render_graph_context(eventlog)

    extras = "\n".join(
        section
        for section in (identity_block, rsm_block, goals_block, graph_block)
        if section
    )
    if body and extras:
        return f"{body}\n\n{extras}"
    if extras:
        return extras
    return body


def selection_digest(
    *, selected: List[int], scores: List[float], model: str, dims: int, query_text: str
) -> str:
    payload = {
        "selected": selected,
        "scores": [float(f"{s:.6f}") for s in scores],
        "model": model,
        "dims": int(dims),
        "query_hash": sha256((query_text or "").encode("utf-8")).hexdigest(),
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(data).hexdigest()


# ----- Phase 2 helpers: durable embeddings (quantized int8) -----


def quantize_int8(vec: List[float]) -> Tuple[List[int], float]:
    """Return (int8_list, scale). scale maps back via x = int8/scale.

    If the vector is all zeros, use scale=1.0 and all zeros.
    """
    max_abs = max((abs(x) for x in vec), default=0.0)
    if max_abs == 0.0:
        return [0] * len(vec), 1.0
    scale = max_abs / 127.0
    ints = [int(max(-128, min(127, round(x / scale)))) for x in vec]
    return ints, float(scale)


def dequantize_int8(ints: List[int], scale: float) -> List[float]:
    if not ints:
        return []
    s = float(scale) if scale else 1.0
    return [i * s for i in ints]


def build_embedding_content(*, event_id: int, text: str, model: str, dims: int) -> str:
    emb = DeterministicEmbedder(model=model, dims=dims).embed(text)
    ints, scale = quantize_int8(emb)
    payload = {
        "event_id": int(event_id),
        "text_hash": sha256((text or "").encode("utf-8")).hexdigest(),
        "model": str(model),
        "dims": int(dims),
        "quant": "int8",
        "scale": float(f"{scale:.9f}"),
        "vector": ints,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def build_index(events: List[Dict], *, model: str, dims: int) -> Dict[int, List[float]]:
    """Return event_id -> dequantized vector for matching model/dims."""
    idx: Dict[int, List[float]] = {}
    for ev in events:
        if ev.get("kind") != "embedding_add":
            continue
        try:
            data = json.loads(ev.get("content") or "{}")
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("model") != model or int(data.get("dims", 0)) != int(dims):
            continue
        eid = int(data.get("event_id", 0))
        vec_ints = data.get("vector") or []
        scale = float(data.get("scale") or 1.0)
        if not isinstance(vec_ints, list):
            continue
        try:
            vec = dequantize_int8([int(x) for x in vec_ints], scale)
        except Exception:
            continue
        idx[eid] = vec
    return idx


def ensure_embedding_for_event(
    *, events: List[Dict], eventlog, event_id: int, text: str, model: str, dims: int
) -> None:
    """Append embedding_add if missing for (event_id, model, dims)."""
    # Check existing
    for ev in events[::-1]:  # scan from end
        if ev.get("kind") != "embedding_add":
            continue
        try:
            data = json.loads(ev.get("content") or "{}")
        except Exception:
            continue
        if (
            isinstance(data, dict)
            and int(data.get("event_id", 0)) == int(event_id)
            and data.get("model") == model
            and int(data.get("dims", 0)) == int(dims)
        ):
            return  # already present
    content = build_embedding_content(
        event_id=event_id, text=text, model=model, dims=dims
    )
    eventlog.append(kind="embedding_add", content=content, meta={})
