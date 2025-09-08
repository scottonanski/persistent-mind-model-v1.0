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


class Runtime:
    def __init__(self, cfg: LLMConfig, eventlog: EventLog) -> None:
        self.cfg = cfg
        self.eventlog = eventlog
        bundle = LLMFactory.from_config(cfg)
        self.chat = bundle.chat
        self.bridge = BridgeManager(model_family=cfg.provider)

    def handle_user(self, user_text: str) -> str:
        msgs = [{"role": "user", "content": user_text}]
        styled = self.bridge.format_messages(msgs, intent="chat")
        reply = self.chat.generate(styled, temperature=1.0)
        self.eventlog.append(kind="response", content=reply, meta={"source": "handle_user"})
        return reply

    def reflect(self, context: str) -> str:
        msgs = [
            {"role": "system", "content": "Reflect briefly on recent progress."},
            {"role": "user", "content": context},
        ]
        styled = self.bridge.format_messages(msgs, intent="reflection")
        note = self.chat.generate(styled, temperature=0.2, max_tokens=256)
        self.eventlog.append(kind="reflection", content=note, meta={"source": "reflect"})
        return note

