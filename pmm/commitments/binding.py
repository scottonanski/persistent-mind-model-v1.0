# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/commitments/binding.py
"""Utilities for deriving execution bindings from commitments."""

from __future__ import annotations

import json

from pmm.core.event_log import EventLog


def extract_exec_binds(eventlog: EventLog, commitment_text: str, cid: str) -> None:
    """Emit exec binding configs derived from the commitment text.

    Currently supports a single deterministic mapping: commitments mentioning
    both "idle" and "monitor" bind the commitment to the "idle_monitor"
    executor with a fixed threshold parameter.
    """

    text = (commitment_text or "").strip()
    if not text or not cid:
        return

    lowered = text.lower()
    if "idle" in lowered and "monitor" in lowered:
        payload = {
            "type": "exec_bind",
            "cid": cid,
            "exec": "idle_monitor",
            "params": {"threshold": 3},
        }
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        eventlog.append(
            kind="config",
            content=content,
            meta={"binding": "auto_detected"},
        )
