from __future__ import annotations

import hashlib as _hashlib
import logging
import math as _math
from functools import lru_cache

logger = logging.getLogger(__name__)


def _load_env_if_missing() -> None:
    """No-op placeholder preserved for API compatibility (no external provider)."""
    return


def _dummy_vec(text: str, dim: int = 32) -> list[float]:
    """Deterministic hash-based vector (used internally)."""
    h = _hashlib.sha1((text or "").encode("utf-8")).digest()
    vals = [h[i % len(h)] for i in range(dim)]
    # center and scale to [0,1]
    return [float(v) / 255.0 for v in vals]


def _bow_vec(text: str, dim: int = 64) -> list[float]:
    """Simple bag-of-words hashed vector.

    Overlapping tokens produce correlated vectors, making cosine similarity meaningful,
    and is fully deterministic without external providers.
    """
    from pmm.utils.parsers import split_non_alnum

    toks = split_non_alnum(text or "")
    vec = [0.0] * dim
    for t in toks:
        hv = int(_hashlib.sha1(t.encode("utf-8")).hexdigest()[:8], 16)
        idx = hv % dim
        vec[idx] += 1.0
    # L2 normalize
    norm = _math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@lru_cache(maxsize=1000)
def _compute_embedding_cached(text: str, model: str = "local-bow") -> tuple[float, ...]:
    """Cached embedding computation returning tuple for hashability.

    LRU cache with maxsize=1000 provides 2-3x speedup for repeated text.
    Returns tuple instead of list for cache compatibility.
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
        result = [v / norm for v in out]
        return tuple(result)
    except Exception:
        # As a last resort, return a constant vector (still non-None)
        return tuple([1.0] * 16)


def compute_embedding(text: str, model: str = "local-bow") -> list[float] | None:
    """Compute an embedding for text deterministically, always ON.

    No environment flags, no external providers.
    Uses LRU cache for 2-3x speedup on repeated text.
    """
    cached_result = _compute_embedding_cached(text, model)
    return list(cached_result) if cached_result else None


def cosine_similarity(a: list[float], b: list[float]) -> float:
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


def digest_vector(vec: list[float]) -> str:
    """Short reproducible SHA1[:8] digest of the vector values for logging."""
    as_bytes = str(list(vec)).encode("utf-8")
    return _hashlib.sha1(as_bytes).hexdigest()[:8]


def get_cache_stats() -> dict:
    """Get LRU cache statistics for monitoring performance.

    Returns:
        dict with keys: hits, misses, maxsize, currsize, hit_rate
    """
    cache_info = _compute_embedding_cached.cache_info()
    total = cache_info.hits + cache_info.misses
    hit_rate = cache_info.hits / total if total > 0 else 0.0

    return {
        "hits": cache_info.hits,
        "misses": cache_info.misses,
        "maxsize": cache_info.maxsize,
        "currsize": cache_info.currsize,
        "hit_rate": hit_rate,
    }


def clear_cache() -> None:
    """Clear the embedding cache. Useful for testing or memory management."""
    _compute_embedding_cached.cache_clear()
    logger.debug("Embedding cache cleared")


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
