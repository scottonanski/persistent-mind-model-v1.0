from __future__ import annotations

from typing import List, Optional
import os as _os
from openai import OpenAI
import hashlib as _hashlib
import math as _math
import re as _re


def _load_env_if_missing() -> None:
    """If OPENAI_API_KEY is missing, attempt to load it from the nearest .env file.

    This avoids requiring users to `source .env` before running tests or code.
    """
    if _os.environ.get("OPENAI_API_KEY"):
        return
    # Search up from this file for a .env
    cur = _os.path.abspath(_os.path.dirname(__file__))
    for _ in range(6):  # search up to 6 levels
        candidate = _os.path.join(cur, ".env")
        if _os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    for line in fh:
                        ln = line.strip()
                        if not ln or ln.startswith("#"):
                            continue
                        if "=" not in ln:
                            continue
                        k, v = ln.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and v and k not in _os.environ:
                            _os.environ[k] = v
            except Exception:
                pass
            break
        parent = _os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent


def _dummy_vec(text: str, dim: int = 32) -> List[float]:
    """Deterministic hash-based vector for tests: PMM_EMBEDDINGS_DUMMY=1."""
    h = _hashlib.sha1((text or "").encode("utf-8")).digest()
    vals = [h[i % len(h)] for i in range(dim)]
    # center and scale to [0,1]
    return [float(v) / 255.0 for v in vals]


def _bow_vec(text: str, dim: int = 64) -> List[float]:
    """Simple bag-of-words hashed vector for tests: TEST_EMBEDDINGS=1.

    Overlapping tokens produce correlated vectors, making cosine similarity meaningful.
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


def compute_embedding(
    text: str, model: str = "text-embedding-3-small"
) -> Optional[List[float]]:
    """Compute an embedding for text.

    Modes:
    - PMM_EMBEDDINGS_DUMMY=1 -> deterministic hash vector via _dummy_vec
    - TEST_EMBEDDINGS=1 -> bag-of-words hashed vector via _bow_vec
    - TEST_EMBEDDINGS_CONSTANT=1 -> constant vector (useful for invariants)
    - Else -> OpenAI embeddings; returns None on failure
    """
    # Test/dummy modes first
    if str(_os.environ.get("TEST_EMBEDDINGS_CONSTANT", "0")).lower() in {"1", "true"}:
        return [1.0] * 16
    if str(_os.environ.get("PMM_EMBEDDINGS_DUMMY", "0")).lower() in {"1", "true"}:
        return _dummy_vec(text)
    if str(_os.environ.get("TEST_EMBEDDINGS", "0")).lower() in {"1", "true"}:
        return _bow_vec(text)

    # Real provider path (OpenAI)
    try:
        _load_env_if_missing()
        client = OpenAI()
        resp = client.embeddings.create(model=model, input=text)
        return resp.data[0].embedding
    except Exception:
        return None


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
    """Compute an embedding and append embedding_indexed or embedding_skipped for the given event id."""
    vec = compute_embedding(text)
    if vec is None:
        eventlog.append(kind="embedding_skipped", content="", meta={})
        return
    try:
        eid_int = int(eid)
    except Exception:
        eid_int = 0
    if eid_int <= 0:
        eventlog.append(kind="embedding_skipped", content="", meta={})
        return
    eventlog.append(
        kind="embedding_indexed",
        content="",
        meta={"eid": eid_int, "digest": digest_vector(vec)},
    )
