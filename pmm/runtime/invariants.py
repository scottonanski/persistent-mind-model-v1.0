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

    # 6) Policy update invariants (reflection cadence + drift multipliers)
    # Helper: stage inference using runtime's tracker without introducing side-effects
    try:
        from pmm.runtime.stage_tracker import StageTracker as _ST
    except Exception:
        _ST = None  # degrade checks if unavailable

    last_pol = None  # (component, params) of the last policy_update
    for idx, ev in enumerate(events):
        if ev.get("kind") != "policy_update":
            continue
        m = ev.get("meta") or {}
        comp = str(m.get("component") or "")
        params = m.get("params") or {}
        st = m.get("stage")

        # (a) No-op duplication forbidden: consecutive duplicates
        key = (comp, params)
        if last_pol == key:
            violations.append("policy:duplicate_policy_update")
            break
        last_pol = key

        # (b) Stage coherence: stage must equal contemporaneous inferred stage
        if _ST is not None:
            try:
                # infer using history strictly before this policy_update
                hist = events[:idx]
                inferred, _snap = _ST.infer_stage(hist)
                inferred = inferred or "S0"
            except Exception:
                inferred = "S0"
            if str(st) != str(inferred):
                violations.append("policy:stage_mismatch")
                # don't break; allow collecting more

        # (c) Component schema
        if comp == "reflection":
            try:
                mt = int(params.get("min_turns"))
                ms = int(params.get("min_time_s"))
                fr = params.get("force_reflect_if_stuck")
                if not isinstance(fr, bool):
                    raise ValueError
                _ = (mt, ms)
            except Exception:
                violations.append("policy:reflection_schema_invalid")
        elif comp == "drift":
            mult = params.get("mult") or {}
            try:
                _ = float(mult["openness"])  # noqa
                _ = float(mult["conscientiousness"])  # noqa
                _ = float(mult["neuroticism"])  # noqa
            except Exception:
                violations.append("policy:drift_schema_invalid")

    # 7) insight_ready one-shot invariants
    # Build id->kind map for quick lookups
    id_kind = {int(ev.get("id") or 0): ev.get("kind") for ev in events}
    # Collect ids by kind for ordering checks
    resp_ids = [int(ev.get("id") or 0) for ev in events if ev.get("kind") == "response"]
    ir_ids = [
        int(ev.get("id") or 0) for ev in events if ev.get("kind") == "insight_ready"
    ]

    for i, ir_id in enumerate(ir_ids):
        # (a) Must reference a prior reflection
        src = None
        for ev in events:
            if int(ev.get("id") or 0) == ir_id:
                src = (ev.get("meta") or {}).get("from_event")
                break
        try:
            src_id = int(src)
        except Exception:
            src_id = -1
        if src_id <= 0 or id_kind.get(src_id) != "reflection" or src_id >= ir_id:
            violations.append("insight:without_preceding_reflection")
            continue

        # (b) Consumed exactly once: count responses after ir_id up to next ir (or EOF)
        next_ir = ir_ids[i + 1] if (i + 1) < len(ir_ids) else None
        consumed = [
            rid
            for rid in resp_ids
            if rid > ir_id and (next_ir is None or rid < next_ir)
        ]
        if len(consumed) == 0:
            violations.append("insight:unconsumed")
        elif len(consumed) > 1:
            violations.append("insight:over_consumed")

    return violations
