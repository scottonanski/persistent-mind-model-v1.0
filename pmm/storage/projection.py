"""Event-to-state projection.

Intent:
- Rebuild the in-memory self-model by replaying events from the event log.
- Minimal, deterministic logic focusing on identity and open commitments.
- Identity substrate: adopt/propose/traits are folded deterministically.
- Optional caching for 5-50x speedup (Phase 2.1 optimization)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pmm.utils.parsers import extract_name_from_change_event, normalize_whitespace

# Fold-time guardrail parameters (tunable)
MAX_TRAIT_DELTA = 0.05  # maximum absolute delta applied per trait_update

# Global projection cache per EventLog instance (Phase 2.1 optimization)
_projection_cache_by_eventlog = {}


class ProjectionInvariantError(ValueError):
    """Raised when strict projection invariants are violated."""

    pass


def build_self_model(
    events: list[dict],
    *,
    strict: bool = False,
    max_trait_delta: float = MAX_TRAIT_DELTA,
    on_warn: Callable[[dict], None] | None = None,
    eventlog=None,
) -> dict:
    """Build a minimal self-model from an ordered list of events.

    Performance: If eventlog is provided and USE_PROJECTION_CACHE=True,
    uses incremental cache for 5-50x speedup. Otherwise uses standard projection.

    Parameters
    ----------
    events : list[dict]
        Rows from `EventLog.read_all()`, ordered by ascending id.
    eventlog : EventLog, optional
        If provided, enables projection cache for performance.
    strict : bool
        Enable strict invariant checking.
    max_trait_delta : float
        Maximum trait delta per event.
    on_warn : callable, optional
        Warning callback for non-strict mode.

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
    # Performance optimization: Use cache if eventlog provided and caching enabled
    if eventlog is not None:
        from pmm.config import USE_PROJECTION_CACHE

        if USE_PROJECTION_CACHE:
            global _projection_cache_by_eventlog
            # Get or create cache for this specific EventLog instance
            cache_key = id(eventlog)
            if cache_key not in _projection_cache_by_eventlog:
                from pmm.storage.projection_cache import ProjectionCache

                _projection_cache_by_eventlog[cache_key] = ProjectionCache(
                    strict=strict,
                    max_trait_delta=max_trait_delta,
                )
            return _projection_cache_by_eventlog[cache_key].get_model(
                eventlog, on_warn=on_warn
            )

    model: dict = {
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
                # Use deterministic parser
                new_name = extract_name_from_change_event(content or "")
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
            # Support both legacy single-trait schema and S4(E) multi-delta schema
            delta_field = meta.get("delta")
            trait = str(meta.get("trait") or "").strip().lower()
            if isinstance(delta_field, dict) and not trait:
                # Multi-delta: apply each trait delta individually
                for k, v in delta_field.items():
                    tkey = key_map.get(str(k).lower())
                    if not tkey:
                        continue
                    try:
                        delta_f = float(v)
                    except Exception:
                        delta_f = 0.0
                    if strict and abs(delta_f) > max_trait_delta:
                        delta_f = max_trait_delta if delta_f > 0 else -max_trait_delta
                    cur = float(model["identity"]["traits"].get(tkey, 0.5))
                    newv = max(0.0, min(1.0, cur + delta_f))
                    model["identity"]["traits"][tkey] = newv
            else:
                # Single-trait legacy path
                try:
                    delta_f = float(delta_field)
                except Exception:
                    delta_f = 0.0
                if strict and abs(delta_f) > max_trait_delta:
                    delta_f = max_trait_delta if delta_f > 0 else -max_trait_delta
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


def build_identity(events: list[dict]) -> dict:
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


def _normalize_directive_text(s: str) -> str:
    """Normalize directive content deterministically (trim + collapse spaces)."""
    return normalize_whitespace(str(s or ""))


def build_directives(events: list[dict]) -> list[dict]:
    """Build a deterministic directives view from autonomy_directive events.

    Returns a list of dicts, each with:
      - content: normalized directive text
      - first_seen_ts: str (ISO timestamp from the first occurrence)
      - last_seen_ts: str (ISO timestamp from the last occurrence)
      - first_seen_id: int (event id of first occurrence)
      - last_seen_id: int (event id of last occurrence)
      - seen_count: int
      - sources: sorted unique list of sources (e.g. ["reflection", "reply"]) from meta.source
      - last_origin_eid: int|None (last non-null origin_eid from meta)
    Sorted by (first_seen_ts, first_seen_id) for stability.
    """
    by_content: dict[str, dict] = {}
    for ev in events:
        if ev.get("kind") != "autonomy_directive":
            continue
        _pay = ev.get("payload") or {}
        raw_content = ev.get("content") or _pay.get("content") or ""
        content = _normalize_directive_text(raw_content)
        meta = (ev.get("meta") or {}) or (_pay.get("meta") or {})
        src = str(meta.get("source") or "").strip().lower()
        try:
            origin_eid = (
                int(meta.get("origin_eid"))
                if meta.get("origin_eid") is not None
                else None
            )
        except Exception:
            origin_eid = None
        ts = ev.get("ts")
        try:
            eid = int(ev.get("id") or 0)
        except Exception:
            eid = 0

        rec = by_content.get(content)
        if rec is None:
            rec = {
                "content": content,
                "first_seen_ts": ts,
                "last_seen_ts": ts,
                "first_seen_id": eid,
                "last_seen_id": eid,
                "seen_count": 1,
                "sources": [src] if src else [],
                "last_origin_eid": origin_eid,
            }
            by_content[content] = rec
        else:
            rec["last_seen_ts"] = ts
            rec["last_seen_id"] = eid
            rec["seen_count"] = int(rec.get("seen_count", 0)) + 1
            if src and src not in rec["sources"]:
                rec["sources"].append(src)
            if origin_eid is not None:
                rec["last_origin_eid"] = origin_eid

    # Finalize: sort sources deterministically and return a stable list
    out: list[dict] = []
    for rec in by_content.values():
        rec["sources"] = sorted([s for s in rec.get("sources", []) if s])
        out.append(rec)
    out.sort(
        key=lambda r: (
            str(r.get("first_seen_ts") or ""),
            int(r.get("first_seen_id") or 0),
        )
    )
    return out


# ---------------- Directive reinforcement (deterministic active set) ----------------
# constants (flag-less)
ACTIVE_TOP_K = 7
RECENT_WEIGHT = 2.0  # recent sightings get a small boost
RECENT_WINDOW = 200  # last-N events considered "recent" for the boost


def build_directives_active_set(events: list[dict]) -> list[dict[str, Any]]:
    """
    Deterministic 'active set' of directives.
    Score = seen_count + RECENT_WEIGHT * recent_hits, then stable-tie-break by (first_seen_id).
    Returns top-K rows with: content, seen_count, recent_hits, score, first_seen_id, last_seen_id, sources.
    """
    base = build_directives(events)

    # index last-N autonomy_directive events for recent_hits
    recent_pool = [e for e in events if e.get("kind") == "autonomy_directive"][
        -RECENT_WINDOW:
    ]
    recent_norms: list[str] = []
    for e in recent_pool:
        # Accept either content or payload.content
        txt = e.get("content")
        if not txt:
            pay = e.get("payload") or {}
            txt = pay.get("content") or ""
        recent_norms.append(_normalize_directive_text(txt))

    from collections import Counter

    c_recent = Counter(recent_norms)

    active: list[dict[str, Any]] = []
    for row in base:
        n = row["content"]  # already normalized by build_directives
        seen = int(row.get("seen_count", 0))
        r_hits = int(c_recent.get(n, 0))
        score = float(seen + RECENT_WEIGHT * r_hits)
        active.append(
            {
                "content": n,
                "seen_count": seen,
                "recent_hits": r_hits,
                "score": score,
                "first_seen_id": row.get("first_seen_id"),
                "last_seen_id": row.get("last_seen_id"),
                "sources": row.get("sources", []),
            }
        )

    # stable ordering: score desc, then first_seen_id asc
    active.sort(key=lambda r: (-float(r["score"]), int(r.get("first_seen_id") or 0)))
    return active[:ACTIVE_TOP_K]
