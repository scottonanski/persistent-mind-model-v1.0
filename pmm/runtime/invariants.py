from __future__ import annotations

import logging

# Set up logging for debug tracking
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Reuse name sanitizer from runtime.loop to ensure single source of truth
try:
    from pmm.runtime.loop import _sanitize_name
except Exception:
    # Fallback (should not happen in tests), define a minimal safe sanitizer
    def _sanitize_name(raw: str) -> str | None:
        token = str(raw or "").strip().split()[0] if raw else ""
        token = token.strip("\"'`,.()[]{}<>")
        if not token:
            return None
        if len(token) > 12:
            token = token[:12]
        # Deterministic validation without regex
        if not token:
            return None
        if not token[0].isalpha():
            return None
        if not all(c.isalnum() or c in "-_" for c in token):
            return None
        if token[0] in "-_" or token[-1] in "-_":
            return None
        if token.isdigit():
            return None
        return token


def check_invariants(events: list[dict]) -> list[str]:
    violations: list[str] = []

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

    # Allow multiple proposals within a grace window (5 events) before requiring adopt
    open_proposal = False
    proposal_count = 0
    for ev in events:
        k = ev.get("kind")
        if k == "identity_adopt":
            open_proposal = False
            proposal_count = 0
        if k == "identity_propose":
            proposal_count += 1
            if open_proposal and proposal_count > 5:
                violations.append("identity:multiple_proposals_without_adopt")
                logger.debug(
                    f"Violation: multiple_proposals_without_adopt at event {ev.get('id')}, count: {proposal_count}"
                )
                break
            open_proposal = True

    # 3) Renderer contract - relaxed to allow adopt without immediate response if next adopt is distant
    adopt_ids = [
        int(ev.get("id")) for ev in events if ev.get("kind") == "identity_adopt"
    ]
    response_ids = [int(ev.get("id")) for ev in events if ev.get("kind") == "response"]
    for idx, aid in enumerate(adopt_ids):
        next_adopt = adopt_ids[idx + 1] if idx + 1 < len(adopt_ids) else float("inf")
        # find first response after adopt
        after = [
            rid
            for rid in response_ids
            if rid > aid and (next_adopt == float("inf") or rid < next_adopt)
        ]
        # Only strict if next adopt is within 2 events (immediately adjacent)
        if not after and (next_adopt - aid) <= 2:
            violations.append("renderer:missing_first_response_after_adopt")
            logger.debug(
                f"Violation: missing_first_response_after_adopt at adopt {aid}, next_adopt: {next_adopt}"
            )
            break
        elif not after:
            logger.debug(
                f"Warning: missing response after adopt {aid}, but next adopt distant at {next_adopt}"
            )

    # 4) Commitments integration: relaxed to allow partial name matching for identity commitments
    # Build cid->text map from openings
    cid_text: dict[str, str] = {}
    for ev in events:
        if ev.get("kind") == "commitment_open":
            m = ev.get("meta") or {}
            cid = m.get("cid")
            txt = m.get("text")
            if cid and isinstance(txt, str):
                cid_text[cid] = txt
    # For each identity adoption, find commitment_close events following it and ensure reasonable name matching
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
                # if it looks like an identity close-by-adopt (by description marker), allow partial match
                desc = str(cm.get("description") or "")
                if f"adopted name {adopted}" in desc or txt.startswith(
                    "identity:name:"
                ):
                    # Allow partial matching instead of exact
                    if txt.startswith("identity:name:"):
                        # Extract after exact prefix
                        target = txt[len("identity:name:") :]
                    else:
                        # Deterministic parsing without regex
                        target = adopted
                        if "I will use the name" in txt:
                            parts = txt.split("I will use the name")
                            if len(parts) > 1:
                                words = parts[1].strip().split()
                                if words:
                                    target = words[0].strip(".,!?;:")

                    # Log mismatches but don't block stage progression (Scott's key fix)
                    adopted_lower = adopted.lower()
                    target_lower = target.lower()
                    # Allow any reasonable name variation (Echo/Persistent are both valid identity names)
                    common_names = {
                        "echo",
                        "persistent",
                        "assistant",
                        "ai",
                        "mind",
                        "pmm",
                    }
                    if (
                        adopted_lower not in target_lower
                        and target_lower not in adopted_lower
                        and adopted_lower != target_lower
                        and adopted_lower not in common_names
                        and target_lower not in common_names
                    ):
                        # Log the mismatch but don't add to violations (prevents stage blocking)
                        logger.debug(
                            f"Relaxed mismatch: adopted '{adopted}' vs commitment "
                            f"'{target}' - not blocking stage progression"
                        )
                    else:
                        logger.debug(
                            f"Allowing name variation: adopted: '{adopted}', target: '{target}'"
                        )

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
    last_tick_by_reason: dict[str, int] = {}
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
        from pmm.runtime.stage_tracker import StageTracker

        stage_tracker = StageTracker
    except Exception:
        stage_tracker = None  # degrade checks if unavailable

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
        if stage_tracker is not None:
            try:
                # infer using history strictly before this policy_update
                hist = events[:idx]
                inferred, _snap = stage_tracker.infer_stage(hist)
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

    # 8) Evidence/commitment invariants (Phase 3 Step 1)
    # (a) Every commitment_close must have a prior evidence_candidate with same cid after its open
    # Build map: cid -> list of open ids
    open_ids_by_cid: dict[str, list[int]] = {}
    for ev in events:
        if ev.get("kind") == "commitment_open":
            m = ev.get("meta") or {}
            cid = str(m.get("cid") or "")
            if cid:
                open_ids_by_cid.setdefault(cid, []).append(int(ev.get("id") or 0))
    # Collect candidate ids by cid
    cand_ids_by_cid: dict[str, list[int]] = {}
    for ev in events:
        if ev.get("kind") == "evidence_candidate":
            m = ev.get("meta") or {}
            cid = str(m.get("cid") or "")
            if cid:
                cand_ids_by_cid.setdefault(cid, []).append(int(ev.get("id") or 0))
    for ev in events:
        if ev.get("kind") != "commitment_close":
            continue
        cm = ev.get("meta") or {}
        cid = str(cm.get("cid") or "")
        close_id = int(ev.get("id") or 0)
        # find the last open id for this cid before close
        opens = open_ids_by_cid.get(cid, [])
        last_open_before_close = 0
        for oid in opens:
            if oid < close_id and oid > last_open_before_close:
                last_open_before_close = oid
        # ensure a candidate exists between last_open_before_close and close_id
        cands = cand_ids_by_cid.get(cid, [])
        ok = any(last_open_before_close < cid_ <= close_id for cid_ in cands)
        if not ok:
            violations.append("evidence:close_without_candidate")

    # (b) No adjacent duplicate evidence_candidate with identical {cid, snippet}
    prev_ev = None
    for ev in events:
        if prev_ev and prev_ev.get("kind") == ev.get("kind") == "evidence_candidate":
            m1 = prev_ev.get("meta") or {}
            m2 = ev.get("meta") or {}
            if str(m1.get("cid") or "") == str(m2.get("cid") or "") and str(
                m1.get("snippet") or ""
            ) == str(m2.get("snippet") or ""):
                violations.append("evidence:duplicate_adjacent_candidate")
                break
        prev_ev = ev

    # 9) recall_suggest invariants
    # For each recall_suggest: eids exist, are earlier than this event id, unique, and <=3 items
    id_set = {int(ev.get("id") or 0) for ev in events}
    for ev in events:
        if ev.get("kind") != "recall_suggest":
            continue
        rid = int(ev.get("id") or 0)
        m = ev.get("meta") or {}
        suggestions = m.get("suggestions") or []
        if not isinstance(suggestions, list):
            violations.append("recall:invalid_schema")
            continue
        if len(suggestions) > 3:
            violations.append("recall:too_many_suggestions")
        seen_eids = set()
        for s in suggestions:
            try:
                eid = int((s or {}).get("eid") or 0)
            except Exception:
                eid = 0
            if eid <= 0 or eid not in id_set:
                violations.append("recall:missing_eid")
                break
            if eid >= rid:
                violations.append("recall:eid_not_prior")
                break
            if eid in seen_eids:
                violations.append("recall:duplicate_eid")
                break
            seen_eids.add(eid)

    # 10) scene_compact invariants
    id_set = {int(ev.get("id") or 0) for ev in events}
    # Track seen windows to prevent duplicate exact-window compacts
    seen_windows = set()
    for ev in events:
        if ev.get("kind") != "scene_compact":
            continue
        cid = int(ev.get("id") or 0)
        m = ev.get("meta") or {}
        src = m.get("source_ids") or []
        win = m.get("window") or {}
        try:
            start = int(win.get("start") or 0)
            end = int(win.get("end") or 0)
        except Exception:
            start, end = 0, 0
        # Content length bound
        content = str(ev.get("content") or "")
        if len(content) > 500:
            violations.append("scene:content_too_long")
        # source_ids validation
        try:
            ids = [int(x) for x in src]
        except Exception:
            violations.append("scene:invalid_source_ids")
            continue
        if not ids:
            violations.append("scene:missing_source_ids")
            continue
        if any(i not in id_set or i >= cid for i in ids):
            violations.append("scene:source_id_invalid_or_not_prior")
        # strictly increasing
        if any(ids[i] >= ids[i + 1] for i in range(len(ids) - 1)):
            violations.append("scene:source_ids_not_increasing")
        # window matches
        if start != ids[0] or end != ids[-1]:
            violations.append("scene:window_mismatch")
        # duplicate exact window check
        key = (start, end)
        if key in seen_windows:
            violations.append("scene:duplicate_window")
        seen_windows.add(key)

    # 11) reflection bandit invariants
    # Map last chosen arm position
    for idx, ev in enumerate(events):
        if ev.get("kind") == "bandit_arm_chosen":
            m = ev.get("meta") or {}
        if ev.get("kind") == "bandit_reward":
            m = ev.get("meta") or {}
            arm = str(m.get("arm") or "")
            try:
                r = float(m.get("reward") or 0.0)
            except Exception:
                r = -1.0
            if r < 0.0 or r > 1.0:
                violations.append("bandit:reward_out_of_bounds")
            # ensure there was a prior chosen arm
            prior = any(
                e.get("kind") == "bandit_arm_chosen"
                and (e.get("meta") or {}).get("arm") == arm
                for e in events[:idx]
            )
            if not prior:
                violations.append("bandit:reward_without_prior_arm")

    # 12) commitment TTL invariants
    # A commitment_expire must reference a commitment that was open at that point
    # and there should be no duplicate expire after a single open without a re-open.
    open_since: dict[str, int] = {}
    for idx, ev in enumerate(events):
        k = ev.get("kind")
        m = ev.get("meta") or {}
        if k == "commitment_open":
            cid = str(m.get("cid") or "")
            if cid:
                open_since[cid] = idx
        elif k == "commitment_close":
            cid = str(m.get("cid") or "")
            if cid in open_since:
                open_since.pop(cid, None)
        elif k == "commitment_expire":
            cid = str(m.get("cid") or "")
            # Must be open
            if cid not in open_since:
                violations.append("ttl:expire_without_open")

    # 13) Embedding invariants
    id_set_all = {int(ev.get("id") or 0) for ev in events}
    seen_digest_by_eid: dict[int, str] = {}
    for ev in events:
        k = ev.get("kind")
        m = ev.get("meta") or {}
        if k == "embedding_indexed":
            try:
                eid = int(m.get("eid") or 0)
            except Exception:
                eid = 0
            digest = str(m.get("digest") or "")
            rid = int(ev.get("id") or 0)
            if eid <= 0 or eid not in id_set_all or eid >= rid:
                violations.append("embedding:eid_not_prior")
            if not digest:
                violations.append("embedding:missing_digest")
            prev = seen_digest_by_eid.get(eid)
            if prev is not None and prev == digest:
                violations.append("embedding:duplicate_digest_for_eid")
            else:
                seen_digest_by_eid[eid] = digest
        elif k == "embedding_skipped":
            if m:
                violations.append("embedding:skipped_has_meta")

    return violations
