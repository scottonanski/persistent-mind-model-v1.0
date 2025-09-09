from __future__ import annotations

import re as _re
from typing import Dict, Optional


class ResponseRenderer:
    """
    Bridge-lite deterministic renderer for assistant replies.

    Responsibilities:
    - Enforce first-person voice by stripping boilerplate like
      "As an AI", "As an assistant", etc.
    - Optionally append a one-time continuity banner after an identity adoption
      event in the form of "— <Name>".
    - No LLM calls; pure string transforms.
    """

    _boilerplate_re = _re.compile(
        r"^\s*(?:As\s+an?\s+(?:AI|assistant|language\s+model)[^,:]*[:,]\s*)",
        _re.IGNORECASE,
    )

    def render(self, raw_text: str, identity: Dict, stage: Optional[str] = None) -> str:
        text = str(raw_text or "").strip()
        # Strip boilerplate lead-ins
        text = self._boilerplate_re.sub("", text).lstrip()

        ident = identity or {}
        name = ident.get("name")
        recent_adopt = bool(ident.get("_recent_adopt"))

        # Append one-time continuity banner after adoption
        if recent_adopt and isinstance(name, str) and name.strip():
            # Skip for ultra-short replies (<=4 visible chars) to avoid awkward micro-signatures
            if len(text.strip()) <= 4:
                return text
            # If the text already ends with a signature like "— Name", avoid duplication
            sig = f"— {name.strip()}"
            # Normalize terminal whitespace before comparison
            tnorm = text.rstrip()
            if not tnorm.endswith(sig):
                # Ensure single trailing newline handling
                if text and not text.endswith("\n"):
                    text = text + "\n"
                text = text + sig
        return text
