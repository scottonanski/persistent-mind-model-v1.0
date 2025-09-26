from __future__ import annotations

from .llm_probe import make_probe_fn
from .capability_resolver import CapabilityResolver
from .generation_controller import GenerationController

_resolver: CapabilityResolver | None = None
_controller: GenerationController | None = None


def _ensure_controller(adapter) -> GenerationController:
    """Return a controller bound to the given adapter.

    If the adapter changes between calls (e.g., tests monkeypatch rt.chat),
    rebuild the resolver and controller so we consistently target the current adapter.
    """
    global _resolver, _controller
    try:
        current = getattr(_controller, "adapter", None)
    except Exception:
        current = None
    if _controller is None or current is not adapter:
        _resolver = CapabilityResolver(probe_fn=make_probe_fn(adapter))
        _controller = GenerationController(adapter=adapter, resolver=_resolver)
    return _controller


def do_chat(
    adapter,
    model_key: str,
    messages: list[dict],
    tooling_on: bool,
    *,
    temperature: float = 0.0,
    task: str = "chat",
    continuation_cap: int = 2,
) -> str:
    ctl = _ensure_controller(adapter)
    text, _stop = ctl.generate_with_budget(
        model_key=model_key,
        messages=messages,
        task=task,
        tooling_on=tooling_on,
        continuation_cap=continuation_cap,
        temperature=temperature,
    )
    return text
