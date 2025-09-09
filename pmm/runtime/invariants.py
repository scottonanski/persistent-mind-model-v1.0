from __future__ import annotations

from typing import List, Dict

# Reuse name sanitizer from runtime.loop to ensure single source of truth
try:
    from pmm.runtime.loop import _sanitize_name
except Exception:
    # Fallback (should not happen in tests), define a minimal safe sanitizer
    import re as _re

    def _sanitize_name(raw: str) -> str | None:
        token = str(raw or "").strip().split()[0] if raw else ""
        token = token.strip("\"'`,.()[]{}<>")
        if not token:
            return None
        if len(token) > 12:
            token = token[:12]
        if not _re.match(r"^[A-Za-z][A-Za-z0-9_-]{0,11}$", token):
            return None
        if token[0] in "-_" or token[-1] in "-_":
            return None
        if token.isdigit():
            return None
        return token


def check_invariants(events: List[Dict]) -> List[str]:
    violations: List[str] = []

    # 1) Ledger shape: ids strictly increasing, kinds are strings, meta is dict
    last_id = 0
    seen_ids = set()
    for ev in events:
        try:
            eid = int(ev.get("id"))
        except Exception:
            violations.append("ledger:id_not_integer")
            eid = last_id
        kind = ev.get("kind")
        if not isinstance(kind, str):
            violations.append("ledger:kind_not_string")
        meta = ev.get("meta")
        if meta is not None and not isinstance(meta, dict):
            violations.append("ledger:meta_not_dict")
        if eid in seen_ids:
            violations.append("ledger:duplicate_id")
        if eid <= last_id:
            violations.append("ledger:non_monotonic_id")
        seen_ids.add(eid)
        last_id = eid

    # 2) Identity substrate checks
    adopted_names = [ev for ev in events if ev.get("kind") == "identity_adopt"]
    if adopted_names:
        last_adopt = adopted_names[-1]
        name = (last_adopt.get("meta") or {}).get("name") or last_adopt.get("content")
        if _sanitize_name(name) is None:
            violations.append("identity:adopted_name_invalid")

    # No multiple proposals without intervening adopt
    open_proposal = False
    for ev in events:
        k = ev.get("kind")
        if k == "identity_adopt":
            open_proposal = False
        if k == "identity_propose":
            if open_proposal:
                violations.append("identity:multiple_proposals_without_adopt")
                break
            open_proposal = True

    # 3) Renderer one-shot contract (ordering sanity)
    # For each adopt, ensure there exists at least one response after it before any next adopt
    adopt_ids = [
        int(ev.get("id")) for ev in events if ev.get("kind") == "identity_adopt"
    ]
    response_ids = [int(ev.get("id")) for ev in events if ev.get("kind") == "response"]
    for idx, aid in enumerate(adopt_ids):
        next_adopt = adopt_ids[idx + 1] if idx + 1 < len(adopt_ids) else None
        # find first response after adopt
        after = [
            rid
            for rid in response_ids
            if rid > aid and (next_adopt is None or rid < next_adopt)
        ]
        if not after:
            violations.append("renderer:missing_first_response_after_adopt")
            break

    # 4) Commitments integration: adoption should close only exact matching identity name commitments
    # Build cid->text map from openings
    cid_text: Dict[str, str] = {}
    for ev in events:
        if ev.get("kind") == "commitment_open":
            m = ev.get("meta") or {}
            cid = m.get("cid")
            txt = m.get("text")
            if cid and isinstance(txt, str):
                cid_text[cid] = txt
    # For each identity adoption, find commitment_close events following it and ensure if description indicates adopted name X,
    # then closed text equals either "identity:name:X" or phrase "I will use the name X" (exact X)
    import re as _re

    for ev in events:
        if ev.get("kind") == "identity_adopt":
            m = ev.get("meta") or {}
            adopted = (m.get("name") or ev.get("content") or "").strip()
            # collect closes after this adopt until next adopt
            aid = int(ev.get("id") or 0)
            for close in events:
                if close.get("kind") != "commitment_close":
                    continue
                if int(close.get("id") or 0) <= aid:
                    continue
                cm = close.get("meta") or {}
                cid = cm.get("cid")
                txt = cid_text.get(cid, "")
                # if it looks like an identity close-by-adopt (by description marker), enforce exact match
                desc = str(cm.get("description") or "")
                if f"adopted name {adopted}" in desc or txt.startswith(
                    "identity:name:"
                ):
                    # exact match only
                    if txt.startswith("identity:name:"):
                        # Extract after exact prefix
                        target = txt[len("identity:name:") :]
                    else:
                        # try to parse name from phrase
                        m2 = _re.search(
                            r"I will use the name\s+([A-Za-z][A-Za-z0-9_-]{0,11})\b",
                            txt,
                        )
                        target = m2.group(1) if m2 else adopted
                    if target != adopted:
                        violations.append("commitments:closed_non_exact_identity_name")
                        break

    # 5) Trait drift invariants
    # No trait_update before first identity_adopt
    first_adopt_id = None
    for ev in events:
        if ev.get("kind") == "identity_adopt":
            first_adopt_id = int(ev.get("id") or 0)
            break
    if first_adopt_id is not None:
        for ev in events:
            if (
                ev.get("kind") == "trait_update"
                and int(ev.get("id") or 0) < first_adopt_id
            ):
                violations.append("drift:trait_update_before_adopt")
                break
    # Rate limits by reason
    last_tick_by_reason: Dict[str, int] = {}
    for ev in events:
        if ev.get("kind") == "trait_update":
            m = ev.get("meta") or {}
            reason = str(m.get("reason") or "")
            try:
                t = int(m.get("tick") or 0)
            except Exception:
                t = 0
            if reason:
                if (
                    reason in last_tick_by_reason
                    and (t - last_tick_by_reason[reason]) < 5
                ):
                    violations.append("drift:rate_limit_violation")
                    break
                last_tick_by_reason[reason] = t

    return violations
