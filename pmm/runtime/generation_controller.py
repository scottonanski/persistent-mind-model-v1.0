from __future__ import annotations
from typing import List, Dict

from .capability_resolver import CapabilityResolver
from .token_budget import allocate_completion_budget, next_continuation_target
from .alloc_tuner import AllocTuner
from .alloc_log import log_alloc


class GenerationController:
    """
    Orchestrates a single generation with:
      - capability resolution
      - task-aware budgeting
      - continuation on stop_reason=length (geometric decay)
    """

    def __init__(self, adapter, resolver: CapabilityResolver):
        self.adapter = adapter
        self.resolver = resolver
        self.tuner = AllocTuner()

    def _count_prompt_tokens(self, messages: List[Dict], model_key: str) -> int:
        # Prefer your adapter's exact tokenizer if exposed; otherwise, adapter should
        # provide a helper. Fallback is 0 (conservative budgeting still holds).
        count_fn = getattr(self.adapter, "count_tokens", None)
        if callable(count_fn):
            try:
                return int(count_fn(model_key=model_key, messages=messages))
            except Exception:
                pass
        return 0

    def generate_with_budget(
        self,
        *,
        model_key: str,
        messages: List[Dict],
        task: str,
        tooling_on: bool,
        continuation_cap: int = 3,
    ):
        # 1) Budget first pass
        prompt_tokens = self._count_prompt_tokens(messages, model_key)
        # Pull per-(model, task) tuner scale
        tuner_scale = self.tuner.get_scale(model_key=model_key, task=task)
        alloc = allocate_completion_budget(
            resolver=self.resolver,
            model_key=model_key,
            prompt_tokens=prompt_tokens,
            task=task,
            tooling_on=tooling_on,
            first_pass=True,
            tuner_scale=tuner_scale,
        )
        max_tokens = alloc.target_out

        chunks: List[str] = []
        k = 0
        last_stop = None
        last_usage = {}

        completion_accum = 0
        while True:
            resp = self.adapter.generate(
                model_key=model_key,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.0,
                return_usage=True,
            )
            text = getattr(resp, "text", "") or ""
            chunks.append(text)
            last_stop = getattr(resp, "stop_reason", None)
            usage = getattr(resp, "usage", None) or {}
            last_usage = usage
            completion_accum += int(usage.get("completion_tokens") or 0)

            if last_stop != "length" or k >= continuation_cap:
                break

            # 2) Carry-over instruction for continuation (no new claims)
            carry = (
                "Continue the same thought from where you stopped. "
                "Do not restart. Finish with one **Actionable Insight** line."
            )
            messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": carry},
            ]

            # 3) Shrink target geometrically to guarantee convergence
            max_tokens = next_continuation_target(max_tokens)
            k += 1

        final_text = "\n".join(chunks).strip()
        # Record outcome to tuner (truth-first telemetry)
        try:
            self.tuner.record(
                model_key=model_key,
                task=task,
                prompt_tokens=prompt_tokens,
                target_out=alloc.target_out,
                completion_tokens=completion_accum,
                stop_reason=last_stop,
            )
        except Exception:
            # non-fatal: tuner errors must not affect generation
            pass

        # Deterministic breadcrumb (no switches)
        try:
            # caps note is embedded in alloc.notes like "caps=source:max_ctx/max_out_hint"
            caps_src = None
            caps_ctx = None
            caps_out = None
            if alloc.notes.startswith("caps="):
                try:
                    # caps=source:ctx/out
                    _, rest = alloc.notes.split("=", 1)
                    src, sizes = rest.split(":", 1)
                    ctx, out = sizes.split("/", 1)
                    caps_src = src
                    caps_ctx = int(ctx)
                    caps_out = int(out)
                except Exception:
                    pass
            log_alloc(
                {
                    "model_key": model_key,
                    "task": task,
                    "policy_id": alloc.policy_id,
                    "prompt_tokens": prompt_tokens,
                    "target_out": alloc.target_out,
                    "completion_tokens": completion_accum,
                    "stop_reason": last_stop,
                    "tuner_scale": tuner_scale,
                    "caps_source": caps_src,
                    "caps_max_ctx": caps_ctx,
                    "caps_max_out_hint": caps_out,
                    "notes": alloc.notes,
                    "continuations": k,
                    "last_usage": last_usage,
                }
            )
        except Exception:
            pass
        return final_text, last_stop
