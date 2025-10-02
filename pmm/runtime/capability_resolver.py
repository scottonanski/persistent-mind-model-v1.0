# pmm/runtime/capability_resolver.py
from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

# --- Types --------------------------------------------------------------------


@dataclass(frozen=True)
class ModelCaps:
    model_key: str  # e.g., "openai/gpt-4o-mini" or "ollama/llama3.2:3b"
    max_ctx: int  # discovered / inferred context window
    max_out_hint: int  # soft upper bound for single completion (task allocator will further clamp)
    discovered_at: float  # epoch seconds
    source: str  # "passive", "probe-ok", "probe-clamped", "fallback"
    notes: str = ""


# Callable signature your runtime must provide for probing:
#   probe_fn(model_key, messages, max_tokens) -> dict with keys:
#     - "ok": bool
#     - "stop_reason": Optional[str]  (e.g., "length", "stop", "error")
#     - "error_code": Optional[str]   (provider error id or string)
#     - "usage": Optional[dict]       (e.g., {"prompt_tokens": int, "completion_tokens": int})
#     - "provider_caps": Optional[dict] e.g., {"max_context": int, "max_output_tokens": int}
ProbeFn = Callable[[str, list, int], dict]

# --- Cache --------------------------------------------------------------------


class _CapsCache:
    def __init__(self, path: str | None = None):
        root = Path(os.getenv("PMM_DATA_DIR", ".data"))
        root.mkdir(parents=True, exist_ok=True)
        self.path = Path(path) if path else root / "model_caps.json"
        self._cache: dict[str, ModelCaps] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                raw = json.load(open(self.path))
                for k, v in raw.items():
                    self._cache[k] = ModelCaps(**v)
            except Exception:
                # corrupt cache: start fresh
                self._cache = {}

    def get(self, key: str) -> ModelCaps | None:
        return self._cache.get(key)

    def put(self, caps: ModelCaps):
        self._cache[caps.model_key] = caps
        tmp = {k: asdict(v) for k, v in self._cache.items()}
        with open(self.path, "w") as f:
            json.dump(tmp, f, indent=2, sort_keys=True)


# --- Resolver -----------------------------------------------------------------

DEFAULT_FALLBACK_CTX = 8192  # conservative for unknowns
DEFAULT_FALLBACK_OUT = 1024

# Conservative candidate output sizes we'll test during probing
_CANDIDATE_OUTS = [4096, 8192, 16384, 32768]  # we will clamp as needed

# Tiny neutral probe message (no semantic effect)
_PROBE_MESSAGES = [{"role": "user", "content": "Say OK."}]


def _hash_model_key(model_key: str) -> str:
    return hashlib.sha256(model_key.encode()).hexdigest()[:8]


class CapabilityResolver:
    """
    Discovers model capabilities via:
      1) Passive read of provider-reported caps (when available)
      2) Active probes with increasing max_tokens to detect clamp/limits
      3) Falls back to safe defaults
    Results are cached under .data/model_caps.json
    """

    def __init__(self, probe_fn: ProbeFn, cache: _CapsCache | None = None):
        self.probe_fn = probe_fn
        self.cache = cache or _CapsCache()

    def ensure_caps(self, model_key: str) -> ModelCaps:
        # 1) Cache hit
        cached = self.cache.get(model_key)
        if cached:
            return cached

        # 2) Passive provider caps (if supplied by probe_fn on a minimal attempt)
        passive = self._passive_try(model_key)
        if passive:
            self.cache.put(passive)
            return passive

        # 3) Active probing (monotonic: we never over-claim)
        probed = self._active_probe(model_key)
        if probed:
            self.cache.put(probed)
            return probed

        # 4) Fallback (truth-first: declare uncertainty)
        fallback = ModelCaps(
            model_key=model_key,
            max_ctx=DEFAULT_FALLBACK_CTX,
            max_out_hint=DEFAULT_FALLBACK_OUT,
            discovered_at=time.time(),
            source="fallback",
            notes="No provider caps; no successful probes.",
        )
        self.cache.put(fallback)
        return fallback

    # --- Internals -------------------------------------------------------------

    def _passive_try(self, model_key: str) -> ModelCaps | None:
        resp = self.probe_fn(model_key, _PROBE_MESSAGES, max_tokens=16)
        prov = (resp or {}).get("provider_caps") or {}
        max_ctx = prov.get("max_context")
        max_out = prov.get("max_output_tokens")
        if isinstance(max_ctx, int) and max_ctx > 0:
            max_out_hint = (
                int(min(max_out or max_ctx // 2, max_ctx))
                if max_ctx
                else DEFAULT_FALLBACK_OUT
            )
            return ModelCaps(
                model_key=model_key,
                max_ctx=int(max_ctx),
                max_out_hint=max(256, max_out_hint),
                discovered_at=time.time(),
                source="passive",
                notes="Provider-reported caps.",
            )
        return None

    def _active_probe(self, model_key: str) -> ModelCaps | None:
        """
        Strategy:
          - Try progressively larger completion sizes.
          - If provider clamps (ok=True but shorter than requested) → record clamp as max_out_hint.
          - If provider errors with "context" or "too many tokens", back off.
          - Infer a conservative max_ctx from usage when available.
        """
        best_out = 0
        inferred_max_ctx = 0
        clamped = False
        last_note = ""
        for candidate in _CANDIDATE_OUTS:
            resp = self.probe_fn(model_key, _PROBE_MESSAGES, max_tokens=candidate)
            if not resp:
                last_note = "no-response"
                break

            usage = resp.get("usage") or {}
            pt = int(usage.get("prompt_tokens") or 0)
            ct = int(usage.get("completion_tokens") or 0)
            stop = resp.get("stop_reason")
            err = resp.get("error_code")

            if pt > 0:
                inferred_max_ctx = max(
                    inferred_max_ctx, pt + max(ct, candidate)
                )  # upper bound heuristic

            if resp.get("ok"):
                # If model stopped normally with fewer tokens than asked, treat as a clamp candidate.
                if stop == "length" or ct < candidate:
                    best_out = max(best_out, ct or candidate)
                    clamped = True
                    last_note = f"ok/clamped at ~{ct or candidate}"
                else:
                    best_out = max(best_out, ct or candidate)
                    last_note = f"ok/{ct or candidate}"
            else:
                # Handle explicit token/context errors
                if err and any(
                    k in err.lower() for k in ["max", "context", "length", "token"]
                ):
                    last_note = f"error:{err}"
                    break
                last_note = f"error:{err or 'unknown'}"
                break

        if best_out == 0 and inferred_max_ctx == 0:
            return None

        # Pick conservative hints
        # If we saw a clamp, trust the clamp size; else use min of best_out and a safe cap.
        hint_out = max(256, min(best_out or DEFAULT_FALLBACK_OUT, 8192))
        # If we could infer context, use it; else default cautiously.
        max_ctx = max(DEFAULT_FALLBACK_CTX, inferred_max_ctx or DEFAULT_FALLBACK_CTX)

        return ModelCaps(
            model_key=model_key,
            max_ctx=int(max_ctx),
            max_out_hint=int(hint_out),
            discovered_at=time.time(),
            source="probe-clamped" if clamped else "probe-ok",
            notes=last_note,
        )
