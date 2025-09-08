"""Bridge manager for prompt/response styling.

Intent:
- Provide a hook for family-aware style handling (e.g., GPT/LLaMA) for a
  consistent voice across chat and reflection.
- For now, `format_messages` is a pass-through and returns a shallow-copied list.
"""

from __future__ import annotations

from typing import List, Dict


class BridgeManager:
    def __init__(self, model_family: str | None = None) -> None:
        self.model_family = (model_family or "").lower()

    def format_messages(self, messages: List[Dict], *, intent: str) -> List[Dict]:
        """Return a new list of messages, potentially applying style rules.

        Currently a no-op pass-through; returns shallow copies to avoid caller
        mutation side-effects.
        """
        return [dict(m) for m in messages]

