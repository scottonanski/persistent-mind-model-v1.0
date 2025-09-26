from __future__ import annotations
from typing import Callable, Any, Dict, List

# This module provides a provider-agnostic probe wrapper around your existing
# ChatAdapter.generate(...) implementation, so CapabilityResolver can discover caps.
#
# Expected adapter API (minimal):
#   adapter.generate(
#       model_key: str,
#       messages: list[dict],
#       *,
#       max_tokens: int,
#       temperature: float = 0.0,
#       return_usage: bool = False,
#   ) -> ResponseLike
# ResponseLike must expose:
#   .text: str
#   .stop_reason: str | None   # e.g., "length", "stop", "content_filter", "error"
#   .usage: dict | None        # {"prompt_tokens": int, "completion_tokens": int}
#   .provider_caps: dict | None  # optional provider-reported caps
#
# If your adapter currently omits any of these fields, you already noted you'll
# enhance it — this wrapper simply passes them through to the resolver.

ProbeFn = Callable[[str, List[dict], int], Dict[str, Any]]


def make_probe_fn(adapter) -> ProbeFn:
    """
    Returns a callable with signature:
        probe(model_key, messages, max_tokens) -> dict
    Safe to pass to CapabilityResolver(probe_fn=...).
    """

    def _probe(model_key: str, messages: list, max_tokens: int) -> dict:
        try:
            try:
                r = adapter.generate(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.0,
                    return_usage=True,
                )
            except TypeError:
                r = adapter.generate(
                    messages=messages, max_tokens=max_tokens, temperature=0.0
                )
            return {
                "ok": True,
                "stop_reason": getattr(r, "stop_reason", None),
                "usage": getattr(r, "usage", None),
                "provider_caps": getattr(r, "provider_caps", None),
            }
        except Exception as e:  # keep broad; resolver only needs a signal
            # If your adapter raises typed errors with .usage/.provider_caps, surface them:
            usage = getattr(e, "usage", None)
            caps = getattr(e, "provider_caps", None)
            code = getattr(e, "code", None) or type(e).__name__
            return {
                "ok": False,
                "error_code": str(code),
                "usage": usage,
                "provider_caps": caps,
            }

    return _probe
