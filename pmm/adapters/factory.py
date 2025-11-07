# Path: pmm/adapters/factory.py
from __future__ import annotations

import os
from typing import Optional

from .__init__ import LLMAdapter
from .dummy_adapter import DummyAdapter
from .openai_adapter import OpenAIAdapter
from .ollama_adapter import OllamaAdapter


class LLMFactory:
    def __init__(self, provider: Optional[str] = None) -> None:
        self.provider = (provider or os.environ.get("PMM_PROVIDER", "dummy")).lower()

    def get(self) -> LLMAdapter:
        if self.provider == "openai":
            return OpenAIAdapter()
        if self.provider == "ollama":
            return OllamaAdapter()
        return DummyAdapter()
