from __future__ import annotations

import os
from pmm.runtime.prompts import SYSTEM_PRIMER


class OpenAIAdapter:
    """OpenAI chat adapter using Chat Completions API.

    Import is deferred to call time to avoid hard dependency during tests.
    """

    def __init__(self, model: str | None = None) -> None:
        # Prefer explicit arg, then PMM-specific var, then common OPENAI_MODEL
        self.model = (
            model
            or os.environ.get("PMM_OPENAI_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or "gpt-4o-mini"
        )

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        # Lazy import
        try:
            import openai  # type: ignore
        except Exception as e:  # pragma: no cover - import error path
            raise RuntimeError("openai package not available") from e

        client = openai.OpenAI() if hasattr(openai, "OpenAI") else None
        if client:
            # new SDK style
            resp = client.chat.completions.create(
                model=self.model,
                temperature=0,
                top_p=1,
                messages=[
                    {
                        "role": "system",
                        "content": f"{SYSTEM_PRIMER}\n\n{system_prompt}",
                    },
                    {"role": "user", "content": user_prompt},
                ],
            )
            return resp.choices[0].message.content or ""
        else:
            # legacy
            resp = openai.ChatCompletion.create(
                model=self.model,
                temperature=0,
                top_p=1,
                messages=[
                    {
                        "role": "system",
                        "content": f"{SYSTEM_PRIMER}\n\n{system_prompt}",
                    },
                    {"role": "user", "content": user_prompt},
                ],
            )
            return resp["choices"][0]["message"]["content"]
