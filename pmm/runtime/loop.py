"""Unified runtime loop using a single chat adapter and bridge.

Intent:
- Single pipeline for user chat and internal reflections.
- Both paths route through the same chat adapter from `LLMFactory.from_config`
  and a `BridgeManager` instance to maintain consistent voice and behavior.
"""

from __future__ import annotations

from pmm.storage.eventlog import EventLog
from pmm.llm.factory import LLMFactory, LLMConfig
from pmm.bridge.manager import BridgeManager
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.metrics import compute_ias_gas


class Runtime:
    def __init__(self, cfg: LLMConfig, eventlog: EventLog) -> None:
        self.cfg = cfg
        self.eventlog = eventlog
        bundle = LLMFactory.from_config(cfg)
        self.chat = bundle.chat
        self.bridge = BridgeManager(model_family=cfg.provider)
        self.cooldown = ReflectionCooldown()

    def handle_user(self, user_text: str) -> str:
        msgs = [{"role": "user", "content": user_text}]
        styled = self.bridge.format_messages(msgs, intent="chat")
        reply = self.chat.generate(styled, temperature=1.0)
        self.eventlog.append(kind="response", content=reply, meta={"source": "handle_user"})
        # Note user turn for reflection cooldown
        self.cooldown.note_user_turn()
        return reply

    def reflect(self, context: str) -> str:
        msgs = [
            {"role": "system", "content": "Reflect briefly on recent progress."},
            {"role": "user", "content": context},
        ]
        styled = self.bridge.format_messages(msgs, intent="reflection")
        note = self.chat.generate(styled, temperature=0.2, max_tokens=256)
        self.eventlog.append(kind="reflection", content=note, meta={"source": "reflect"})
        # Emit telemetry after reflection
        ias, gas = compute_ias_gas(self.eventlog.read_all())
        self.eventlog.append(kind="telemetry", content="", meta={"IAS": ias, "GAS": gas})
        # Reset cooldown on successful reflection
        self.cooldown.reset()
        return note


def evaluate_reflection(cooldown: ReflectionCooldown, *, now: float | None = None, novelty: float = 1.0) -> tuple[bool, str]:
    """Tiny helper to evaluate reflection cooldown without wiring full loop.

    Returns (should_reflect, reason).
    """
    return cooldown.should_reflect(now=now, novelty=novelty)


def emit_reflection(eventlog: EventLog, content: str = "") -> None:
    """Emit a simple reflection event (used where real chat isn't wired)."""
    eventlog.append(kind="reflection", content=content or "(reflection)", meta={"source": "emit_reflection"})
    # After reflection, emit telemetry snapshot
    ias, gas = compute_ias_gas(eventlog.read_all())
    eventlog.append(kind="telemetry", content="", meta={"IAS": ias, "GAS": gas})


def maybe_reflect(eventlog: EventLog, cooldown: ReflectionCooldown, *, now: float | None = None, novelty: float = 1.0) -> tuple[bool, str]:
    """Check cooldown gates; emit reflection or breadcrumb debug event.

    Returns (did_reflect, reason). If skipped, reason is the gate name.
    """
    ok, reason = cooldown.should_reflect(now=now, novelty=novelty)
    if not ok:
        eventlog.append(kind="debug", content="", meta={"reflect_skip": reason})
        return (False, reason)
    emit_reflection(eventlog)
    cooldown.reset()
    return (True, "ok")

