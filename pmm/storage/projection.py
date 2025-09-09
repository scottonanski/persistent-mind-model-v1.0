"""Event-to-state projection.

Intent:
- Rebuild the in-memory self-model by replaying events from the event log.
- Minimal, deterministic logic focusing on identity and open commitments.
"""

from __future__ import annotations

import re as _re
from typing import Dict, List


def build_self_model(events: List[Dict]) -> Dict:
    """Build a minimal self-model from an ordered list of events.

    Parameters
    ----------
    events : list[dict]
        Rows from `EventLog.read_all()`, ordered by ascending id.

    Returns
    -------
    dict
        Minimal self-model:
        {
          "identity": {"name": str|None},
          "commitments": {"open": {cid: {"text": str, ...}}}
        }
    """

    model: Dict = {
        "identity": {"name": None},
        "commitments": {"open": {}},
    }

    name_pattern = _re.compile(r"Name\s+changed\s+to:\s*(?P<name>.+)", _re.IGNORECASE)

    for ev in events:
        kind = ev.get("kind")
        content = ev.get("content", "")
        meta = ev.get("meta") or {}

        if kind == "identity_change":
            # Prefer explicit meta name
            new_name = meta.get("name")
            if not new_name:
                m = name_pattern.search(content or "")
                if m:
                    new_name = m.group("name").strip()
            if new_name:
                model["identity"]["name"] = new_name

        elif kind == "commitment_open":
            cid = meta.get("cid")
            text = meta.get("text")
            if cid and text is not None:
                # Store text and any useful extra fields
                entry = {k: v for k, v in meta.items()}
                model["commitments"]["open"][cid] = entry

        elif kind == "commitment_close":
            cid = meta.get("cid")
            if cid and cid in model["commitments"]["open"]:
                model["commitments"]["open"].pop(cid, None)

    return model
