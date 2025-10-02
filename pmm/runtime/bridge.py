from __future__ import annotations


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

    def _strip_boilerplate(self, text: str) -> str:
        """Strip boilerplate lead-ins deterministically."""
        if not text:
            return text

        # Check for common boilerplate patterns at start
        text_lower = text.lower().lstrip()
        boilerplate_patterns = [
            "as an ai",
            "as an assistant",
            "as a language model",
            "as an ai assistant",
        ]

        for pattern in boilerplate_patterns:
            if text_lower.startswith(pattern):
                # Find the end of the boilerplate (usually ends with : or ,)
                rest = text[len(pattern) :]
                # Skip past any punctuation and whitespace
                for i, char in enumerate(rest):
                    if char in ":,":
                        return rest[i + 1 :].lstrip()
                    elif char.isalpha():
                        # No punctuation found, pattern didn't match fully
                        break

        return text

    def render(
        self,
        raw_text: str,
        *,
        identity: dict | None = None,
        recent_adopt_id: int | None = None,
        events: list[dict] | None = None,
    ) -> str:
        text = str(raw_text or "").strip()
        # Strip boilerplate lead-ins (deterministic)
        text = self._strip_boilerplate(text)

        ident = identity or {}
        # One-shot identity continuity signature banner when recent adopt
        try:
            nm = ident.get("name")
            if nm and recent_adopt_id is not None:
                # Avoid awkward micro-signatures for ultra-short replies (<=4 chars)
                if len(text.strip()) <= 4:
                    return text
                # Avoid duplicating if already present
                if not text.rstrip().endswith(f"— {nm}"):
                    if text and not text.endswith("\n"):
                        text = text + "\n"
                    text = text + f"— {nm}"
        except Exception:
            pass

        # One-shot Insight line: only when events are provided
        if events is None:
            return text

        # Overlay always enabled (no env gate)
        # Find most recent insight_ready
        ir = None
        for ev in reversed(events):
            if ev.get("kind") == "insight_ready":
                ir = ev
                break
        if not ir:
            return text
        ir_id = int(ir.get("id") or 0)
        src_id = int((ir.get("meta") or {}).get("from_event") or 0)
        # Find last response id before this render
        last_resp_id = None
        for ev in reversed(events):
            if ev.get("kind") == "response":
                last_resp_id = int(ev.get("id") or 0)
                break
        # One-shot condition: only if no response after the insight_ready
        if last_resp_id is not None and last_resp_id >= ir_id:
            return text

        # Resolve the source reflection content
        src_text = ""
        for ev in reversed(events):
            if int(ev.get("id") or 0) == src_id and ev.get("kind") == "reflection":
                src_text = str(ev.get("content") or "")
                break

        # Deterministic paraphrase
        def _strip_markdown(s: str) -> str:
            from pmm.utils.parsers import (
                normalize_whitespace,
                strip_markdown_formatting,
            )

            return normalize_whitespace(strip_markdown_formatting(s or ""))

        def _first_sentence(s: str) -> str:
            from pmm.utils.parsers import extract_first_sentence

            return extract_first_sentence(s or "")

        paraphrase = _first_sentence(_strip_markdown(src_text))
        if len(paraphrase) > 140:
            paraphrase = paraphrase[:140].rstrip()

        # Guard: if an insight overlay already exists in the text (e.g., due to a prior
        # render and a subsequent re-render like voice correction), do not append again.
        if paraphrase and ("_Insight:" not in text):
            if text and not text.endswith("\n"):
                text = text + "\n"
            text = text + f"_Insight:_ {paraphrase}"
        return text
