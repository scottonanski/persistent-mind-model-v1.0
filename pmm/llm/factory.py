"""Unified LLM factory (skeleton).

Intent:
- Provide `from_config(cfg)` that returns a bundle of adapters
  (chat + embed) based on a single configuration.
- Centralize provider/model selection so all LLM usage funnels here.
"""
