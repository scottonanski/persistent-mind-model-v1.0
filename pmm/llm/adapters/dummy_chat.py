"""Dummy chat adapter for testing (deterministic, no external calls)."""

from __future__ import annotations

from typing import List, Dict
import hashlib
import json


class DummyChat:
    """Dummy chat adapter for testing purposes.

    Returns deterministic responses based on input hash.
    """

    def __init__(self, model: str, **kw) -> None:
        self.model = model
        self.kw = kw

    def generate(self, messages: List[Dict], **kwargs) -> str:
        """Generate a deterministic response based on input messages."""
        # Create a deterministic hash of the input
        input_str = json.dumps(messages, sort_keys=True)
        hash_obj = hashlib.sha256(input_str.encode())
        hash_hex = hash_obj.hexdigest()

        # Return a simple response based on the hash
        response = f"Dummy response for {self.model} (hash: {hash_hex[:8]})"
        return response
