"""OpenAI embedding adapter using urllib with simple retries.

Env vars:
- OPENAI_API_KEY: API key (required)
- OPENAI_BASE_URL: Base URL (default: https://api.openai.com)
- OPENAI_REQUEST_TIMEOUT_SECONDS: float seconds (default: 20.0)
- OPENAI_REQUEST_MAX_RETRIES: int retries (default: 2)
"""

from __future__ import annotations

from typing import List
import os
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class OpenAIEmbed:
    """Tiny placeholder for an OpenAI embedding adapter.

    Stores the model name and exposes an `embed` method signature compatible
    with `EmbeddingAdapter`, but does not perform any network calls.
    """

    def __init__(self, model: str, **kw) -> None:
        self.model = model
        self.kw = kw
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
        # v1/embeddings endpoint
        self.endpoint = f"{base}/v1/embeddings"

    # local env helpers (avoid importing project-wide utils to keep adapter standalone)
    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except Exception:
            return float(default)

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except Exception:
            return int(default)

    def embed(
        self, texts: List[str]
    ) -> List[List[float]]:  # pragma: no cover - not invoked here
        # Implementation replaced: see below
        if texts is None:
            texts = []
        if isinstance(texts, str):
            texts = [texts]
        texts = [str(t) for t in texts if t is not None]
        if not texts:
            return []

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set (put it in .env)")

        req_timeout = self._env_float("OPENAI_REQUEST_TIMEOUT_SECONDS", 20.0)
        max_retries = self._env_int("OPENAI_REQUEST_MAX_RETRIES", 2)

        payload = {"model": self.model, "input": texts}
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        print(
            f"[openai] POST {self.endpoint} model={self.model} n_inputs={len(texts)} "
            f"timeout={req_timeout}s retries={max_retries}",
            file=sys.stderr,
            flush=True,
        )

        attempt = 0
        last_exc: Exception | None = None
        while attempt <= max_retries:
            try:
                req = Request(self.endpoint, data=body, headers=headers, method="POST")
                with urlopen(req, timeout=req_timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                arr = data.get("data")
                if not isinstance(arr, list) or len(arr) != len(texts):
                    raise RuntimeError(
                        f"Unexpected embeddings response: {str(data)[:300]}"
                    )
                out: List[List[float]] = []
                for i, item in enumerate(arr):
                    emb = item.get("embedding")
                    if not isinstance(emb, list) or not emb:
                        raise RuntimeError(
                            f"Missing embedding at index {i}: {str(item)[:200]}"
                        )
                    try:
                        out.append([float(x) for x in emb])
                    except Exception:
                        raise RuntimeError(f"Non-numeric embedding at index {i}")
                return out

            except HTTPError as e:
                status = getattr(e, "code", None)
                retriable = status in (429,) or (
                    isinstance(status, int) and 500 <= status < 600
                )
                try:
                    err_body = e.read().decode("utf-8")[:800]
                except Exception:
                    err_body = ""
                if attempt < max_retries and retriable:
                    time.sleep(min(0.25 * (2**attempt), 4.0))
                    attempt += 1
                    last_exc = e
                    continue
                raise RuntimeError(
                    f"OpenAI HTTP {status}: {e.reason}; body={err_body}"
                ) from e

            except URLError as e:
                if attempt < max_retries:
                    time.sleep(min(0.25 * (2**attempt), 4.0))
                    attempt += 1
                    last_exc = e
                    continue
                raise RuntimeError(
                    f"OpenAI network error: {getattr(e, 'reason', e)}"
                ) from e

            except Exception as e:
                if attempt < max_retries:
                    time.sleep(min(0.25 * (2**attempt), 4.0))
                    attempt += 1
                    last_exc = e
                    continue
                raise

        if last_exc:
            raise RuntimeError(
                f"OpenAIEmbed.embed exhausted retries: {last_exc}"
            ) from last_exc
        raise RuntimeError("OpenAIEmbed.embed failed without error (unexpected)")
