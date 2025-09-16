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

    def render(
        self,
        raw_text: str,
        identity: Dict,
        stage: Optional[str] = None,
        *,
        events: Optional[list[dict]] = None,
    ) -> str:
        text = str(raw_text or "").strip()
        # Strip boilerplate lead-ins
        text = self._boilerplate_re.sub("", text).lstrip()

        ident = identity or {}
        # One-shot identity continuity signature banner when recent adopt
        try:
            nm = ident.get("name")
            if nm and ident.get("_recent_adopt"):
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
            s = str(s or "")
            # Remove fenced code blocks
            s = _re.sub(r"```[\s\S]*?```", " ", s)
            # Remove inline code/backticks
            s = s.replace("`", " ")
            # Remove emphasis markers
            s = s.replace("**", " ").replace("*", " ").replace("_", " ")
            # Collapse whitespace
            s = _re.sub(r"\s+", " ", s).strip()
            return s

        def _first_sentence(s: str) -> str:
            # Split on . ! ? or newline
            parts = _re.split(r"[\.!?\n]", s, maxsplit=1)
            return (parts[0] or "").strip()

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
