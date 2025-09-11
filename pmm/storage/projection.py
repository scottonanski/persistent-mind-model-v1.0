"""Event-to-state projection.

Intent:
- Rebuild the in-memory self-model by replaying events from the event log.
- Minimal, deterministic logic focusing on identity and open commitments.
- Identity substrate: adopt/propose/traits are folded deterministically.
"""

from __future__ import annotations

import re as _re
from typing import Dict, List, Optional, Callable

# Fold-time guardrail parameters (tunable)
MAX_TRAIT_DELTA = 0.05  # maximum absolute delta applied per trait_update


class ProjectionInvariantError(ValueError):
    """Raised when strict projection invariants are violated."""

    pass


def build_self_model(
    events: List[Dict],
    *,
    strict: bool = False,
    max_trait_delta: float = MAX_TRAIT_DELTA,
    on_warn: Optional[Callable[[Dict], None]] = None,
) -> Dict:
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
          "identity": {
              "name": str|None,
              "traits": {"openness": float, "conscientiousness": float,
                          "extraversion": float, "agreeableness": float,
                          "neuroticism": float}
          },
          "commitments": {"open": {cid: {"text": str, ...}}}
        }
    """

    model: Dict = {
        "identity": {
            "name": None,
            "traits": {
                "openness": 0.5,
                "conscientiousness": 0.5,
                "extraversion": 0.5,
                "agreeableness": 0.5,
                "neuroticism": 0.5,
            },
        },
        "commitments": {"open": {}, "expired": {}},
    }

    name_pattern = _re.compile(r"Name\s+changed\s+to:\s*(?P<name>.+)", _re.IGNORECASE)

    # Track seen evidence to enforce close-after-evidence ordering
    _evidence_seen: set[tuple] = set()  # (cid, evidence_type)
    # Track whether an identity was ever adopted to prevent silent reversion
    _identity_adopted = False
    _last_eid: int = 0

    for ev in events:
        kind = ev.get("kind")
        content = ev.get("content", "")
        meta = ev.get("meta") or {}
        try:
            _last_eid = int(ev.get("id") or 0)
        except Exception:
            _last_eid = 0

        if kind == "identity_change":
            # Prefer explicit meta name
            new_name = meta.get("name")
            if not new_name:
                m = name_pattern.search(content or "")
                if m:
                    new_name = m.group("name").strip()
            if new_name:
                model["identity"]["name"] = new_name

        elif kind == "identity_adopt":
            # Last writer wins for name
            new_name = meta.get("name") or content or None
            if isinstance(new_name, str):
                nm = new_name.strip()
                model["identity"]["name"] = nm or None
                if nm:
                    _identity_adopted = True

        elif kind == "identity_clear":
            # Explicit identity clear (used to avoid strict revert error)
            model["identity"]["name"] = None
            _identity_adopted = False

        elif kind == "trait_update":
            # Cumulative delta with per-event bound and clamp [0,1]
            trait = str(meta.get("trait") or "").strip().lower()
            delta = meta.get("delta")
            try:
                delta_f = float(delta)
            except Exception:
                delta_f = 0.0
            # Enforce per-event absolute delta bound only in strict mode
            if strict and abs(delta_f) > max_trait_delta:
                delta_f = max_trait_delta if delta_f > 0 else -max_trait_delta
            key_map = {
                "o": "openness",
                "openness": "openness",
                "c": "conscientiousness",
                "conscientiousness": "conscientiousness",
                "e": "extraversion",
                "extraversion": "extraversion",
                "a": "agreeableness",
                "agreeableness": "agreeableness",
                "n": "neuroticism",
                "neuroticism": "neuroticism",
            }
            tkey = key_map.get(trait)
            if tkey:
                cur = float(model["identity"]["traits"].get(tkey, 0.5))
                newv = max(0.0, min(1.0, cur + delta_f))
                model["identity"]["traits"][tkey] = newv

        elif kind == "commitment_open":
            cid = meta.get("cid")
            text = meta.get("text")
            if cid and text is not None:
                # Store text and any useful extra fields
                entry = {k: v for k, v in meta.items()}
                model["commitments"]["open"][cid] = entry

        elif kind == "evidence_candidate":
            cid = meta.get("cid")
            et = (meta.get("evidence_type") or "done").strip().lower()
            if cid:
                _evidence_seen.add((cid, et))

        elif kind in ("commitment_close", "commitment_expire"):
            cid = meta.get("cid")
            if cid and cid in model["commitments"]["open"]:
                if kind == "commitment_close":
                    # strict ordering: require evidence first
                    if (cid, "done") not in _evidence_seen:
                        if strict:
                            raise ProjectionInvariantError(
                                f"commitment_close without prior evidence_candidate (cid={cid}, eid={_last_eid})"
                            )
                        # Non-strict: proceed with close but optionally emit telemetry hook
                        if callable(on_warn):
                            try:
                                on_warn(
                                    {
                                        "kind": "projection_warn",
                                        "content": "commitment_close without evidence",
                                        "meta": {
                                            "cid": cid,
                                            "eid": _last_eid,
                                            "reason": "close_without_evidence",
                                        },
                                    }
                                )
                            except Exception:
                                # Never allow telemetry hook to break projection
                                pass
                # If expire, record in expired section
                if kind == "commitment_expire":
                    model["commitments"]["expired"][cid] = {
                        "text": model["commitments"]["open"][cid].get("text"),
                        "expired_at": int(ev.get("id") or 0),
                        "reason": (meta or {}).get("reason") or "timeout",
                    }
                model["commitments"]["open"].pop(cid, None)
        elif kind == "commitment_snooze":
            cid = meta.get("cid")
            if cid and cid in model["commitments"]["open"]:
                try:
                    until_t = int(meta.get("until_tick") or 0)
                except Exception:
                    until_t = 0
                model["commitments"]["open"][cid]["snoozed_until"] = until_t

    # Final identity invariant (strict mode): if identity was adopted, it must not end as None
    if strict and _identity_adopted and (model["identity"].get("name") is None):
        raise ProjectionInvariantError(
            f"identity reverted to None without identity_clear (last_eid={_last_eid})"
        )

    return model


def build_identity(events: List[Dict]) -> Dict:
    """Return the folded identity view only.

    Structure: {"name": str|None, "traits": {...}}
    """
    m = build_self_model(events)
    ident = m.get("identity") or {}
    # Ensure full trait keys present
    traits = ident.get("traits") or {}
    for k in [
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
    ]:
        traits[k] = float(traits.get(k, 0.5))
    return {"name": ident.get("name"), "traits": traits}
