"""Unified runtime loop (skeleton).

Intent:
- Single pipeline for user chat and internal reflections.
- Both paths route through LLM factory-provided chat adapter and bridge manager
  for consistent model usage and voice.
"""
