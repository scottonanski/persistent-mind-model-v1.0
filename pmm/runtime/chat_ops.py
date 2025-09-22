from __future__ import annotations

from .llm_probe import make_probe_fn
from .capability_resolver import CapabilityResolver
from .generation_controller import GenerationController

_resolver: CapabilityResolver | None = None
_controller: GenerationController | None = None


def _ensure_controller(adapter) -> GenerationController:
    global _resolver, _controller
    if _resolver is None:
        _resolver = CapabilityResolver(probe_fn=make_probe_fn(adapter))
    if _controller is None:
        _controller = GenerationController(adapter=adapter, resolver=_resolver)
    return _controller


def do_chat(adapter, model_key: str, messages: list[dict], tooling_on: bool) -> str:
    ctl = _ensure_controller(adapter)
    text, _stop = ctl.generate_with_budget(
        model_key=model_key,
        messages=messages,
        task="chat",
        tooling_on=tooling_on,
        continuation_cap=2,
    )
    return text
