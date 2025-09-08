"""Commitment tracking (skeleton).

Intent:
- Minimal lifecycle: add, list open, close with explicit evidence events.
- Integrates with storage.eventlog for persistence (single source of truth).
- Evidence-first closure only; no heuristic autoclose.
"""
