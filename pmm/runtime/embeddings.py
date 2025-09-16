from __future__ import annotations

from typing import List, Optional
import hashlib as _hashlib
import math as _math
import re as _re


def _load_env_if_missing() -> None:
    """No-op placeholder preserved for API compatibility (no external provider)."""
    return


def _dummy_vec(text: str, dim: int = 32) -> List[float]:
    """Deterministic hash-based vector (used internally)."""
    h = _hashlib.sha1((text or "").encode("utf-8")).digest()
    vals = [h[i % len(h)] for i in range(dim)]
    # center and scale to [0,1]
    return [float(v) / 255.0 for v in vals]


def _bow_vec(text: str, dim: int = 64) -> List[float]:
    """Simple bag-of-words hashed vector.

    Overlapping tokens produce correlated vectors, making cosine similarity meaningful,
    and is fully deterministic without external providers.
    """
    s = (text or "").lower()
    toks = [t for t in _re.split(r"[^a-z0-9]+", s) if t]
    vec = [0.0] * dim
    for t in toks:
        hv = int(_hashlib.sha1(t.encode("utf-8")).hexdigest()[:8], 16)
        idx = hv % dim
        vec[idx] += 1.0
    # L2 normalize
    norm = _math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def compute_embedding(text: str, model: str = "local-bow") -> Optional[List[float]]:
    """Compute an embedding for text deterministically, always ON.

    No environment flags, no external providers.
    """
    # Primary: bag-of-words hashed vector
    try:
        vec = _bow_vec(text)
        # Small jitter via dummy mix to reduce identical digests for short inputs
        dv = _dummy_vec(text)
        n = min(len(vec), len(dv))
        out = [float(0.9 * vec[i] + 0.1 * dv[i]) for i in range(n)]
        # Renormalize
        norm = _math.sqrt(sum(v * v for v in out)) or 1.0
        return [v / norm for v in out]
    except Exception:
        # As a last resort, return a constant vector (still non-None)
        return [1.0] * 16


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Stable cosine similarity between two vectors."""
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = _math.sqrt(sum(float(a[i]) * float(a[i]) for i in range(n)))
    nb = _math.sqrt(sum(float(b[i]) * float(b[i]) for i in range(n)))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(dot / (na * nb))


def digest_vector(vec: List[float]) -> str:
    """Short reproducible SHA1[:8] digest of the vector values for logging."""
    as_bytes = str(list(vec)).encode("utf-8")
    return _hashlib.sha1(as_bytes).hexdigest()[:8]


def index_and_log(eventlog, eid: int, text: str) -> None:
    """Compute an embedding and append embedding_indexed for the given event id (always ON)."""
    vec = compute_embedding(text)
    try:
        eid_int = int(eid)
    except Exception:
        eid_int = 0
    if eid_int <= 0:
        return
    eventlog.append(
        kind="embedding_indexed",
        content="",
        meta={"eid": eid_int, "digest": digest_vector(vec)},
    )
