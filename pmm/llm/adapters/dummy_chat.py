"""Dummy chat adapter for testing (deterministic, no external calls)."""

from __future__ import annotations

from typing import List, Dict, Iterator
import hashlib
import json
import time


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

    def generate_stream(self, messages: List[Dict], **kwargs) -> Iterator[str]:
        """Stream a deterministic response token by token.

        Simulates streaming by yielding words with small delays.
        """
        # Generate the full response
        response = self.generate(messages, **kwargs)

        # Stream it word by word
        words = response.split()
        for i, word in enumerate(words):
            # Add space before all words except the first
            if i > 0:
                yield " "
            yield word
            # Small delay to simulate network latency (only in tests)
            if kwargs.get("simulate_delay", False):
                time.sleep(0.01)
