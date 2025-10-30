"""Anti-hallucination validators (Stage 4 extraction).

Extracts commitment and event ID validation functions from monolithic loop.py.
All behavior preserved exactly as-is per CONTRIBUTING.md.
"""

from __future__ import annotations

import logging
from typing import Any

from pmm.commitments.intent_detector import (
    extract_commitment_claims as _extract_commitment_claims_semantic,
)
from pmm.runtime.embeddings import compute_embedding, cosine_similarity
from pmm.runtime.loop import io as _io
from pmm.storage.eventlog import EventLog
from pmm.utils.parsers import (
    extract_closed_commitment_claims,
    extract_event_ids,
    parse_commitment_refs,
)
from pmm.utils.parsers import (
    extract_commitment_claims as _extract_commitment_claims_keywords,
)

logger = logging.getLogger(__name__)


def verify_event_existence_claims(
    reply: str, eventlog: EventLog
) -> tuple[bool, list[str]]:
    """Validate claims about the existence of event kinds in the ledger."""

    if not reply:
        return True, []

    text = f" {reply.strip().lower()} "
    candidate_kinds = [
        "commitment_open",
        "commitment_close",
        "commitment_expire",
        "stage_update",
        "identity_adopt",
        "trait_update",
        "policy_update",
        "reflection",
    ]
    patterns = [
        " there is a {k} event",
        " there is an {k} event",
        " the ledger shows {k}",
        " i found a {k} event",
        " shows a {k} event",
    ]

    claimed: set[str] = set()
    for kind in candidate_kinds:
        for pat in patterns:
            if pat.format(k=kind) in text:
                claimed.add(kind)
                break

    if not claimed:
        return True, []

    missing: list[str] = []
    for kind in sorted(claimed):
        try:
            count = eventlog.count_events(kind)
        except Exception:
            count = 0
        if count <= 0:
            missing.append(kind)

    return (len(missing) == 0, missing)


def verify_commitment_claims(reply: str, eventlog: EventLog) -> tuple[bool, str | None]:
    """Verify that commitment claims in LLM response match ledger reality.

    This is a post-response validator that catches commitment hallucinations.
    It only runs if the response mentions "commit" to minimize overhead.

    Args:
        reply: The LLM's response text
        eventlog: Ledger interface for querying commitment state

    Returns:
        (hallucination_detected, correction_message):
            - True if hallucination detected, False otherwise
            - Correction message to inject into next prompt, or None

    Side effects:
        Logs warnings if mismatches are detected
        Prints user-friendly emoji message when hallucination found
    """
    # Lazy validation: check if response might contain commitment-related content
    # Include broader triggers to catch semantic commitments
    reply_lower = reply.lower()
    commitment_indicators = [
        "commit",
        "i will",
        "i'll",
        "i plan",
        "my goal",
        "i need to",
        "i must",
    ]
    if not any(indicator in reply_lower for indicator in commitment_indicators):
        return (False, None)

    # Extract numeric claims via keyword parser (e.g., "event id 21")
    numeric_claims: list[str] = []
    for c in _extract_commitment_claims_keywords(reply):
        if isinstance(c, str) and c.isdigit():
            numeric_claims.append(c)

    # Extract semantic "open" commitment sentences (first-person pledges)
    # Use moderately high threshold (0.80) with contextual filters to balance precision/recall
    semantic_claims: list[str] = []
    for sent, intent, conf in _extract_commitment_claims_semantic(
        reply, threshold=0.80
    ):
        # Additional filters to reduce false positives:
        # 1. Skip very short sentences (acknowledgments)
        # 2. Must have sufficient length to be a real commitment
        words = sent.split()
        if len(words) > 5:  # More than 5 words for substantive commitments
            # Skip common conversational openings that aren't commitments
            sent_lower = sent.lower().strip()
            conversational_starts = [
                "i apologize",
                "that's a",
                "it's a",
                "i'm ready",
                "okay",
                "great",
                "thanks",
                "sure",
                "yes",
                "just let me know",
                "how can i",
                "i'll do my best",
                "let me know",
                "i can help",
            ]
            if not any(sent_lower.startswith(start) for start in conversational_starts):
                semantic_claims.append(sent)

    # Unified claims list: numeric event ids + semantic text sentences
    claimed_commitments = list(numeric_claims) + list(semantic_claims)

    if not claimed_commitments:
        return (False, None)  # No specific claims to verify

    # Build current self-model to determine which commitments remain open
    from pmm.storage.projection import build_self_model

    try:
        events = eventlog.read_all()
    except Exception:
        logger.warning("Failed to read ledger for commitment validation", exc_info=True)
        return (False, None)

    model = build_self_model(events, eventlog=eventlog)
    open_commitments = (model.get("commitments") or {}).get("open") or {}

    # Map commitment IDs to their originating event IDs for numeric claim checks
    open_event_ids: dict[str, int] = {}
    for ev in events:
        if ev.get("kind") != "commitment_open":
            continue
        meta = ev.get("meta") or {}
        cid = str(meta.get("cid") or "")
        if cid and cid in open_commitments and cid not in open_event_ids:
            try:
                open_event_ids[cid] = int(ev.get("id") or 0)
            except Exception:
                open_event_ids[cid] = 0

    actual_commitments: list[dict[str, Any]] = []
    for cid, entry in open_commitments.items():
        raw_text = str((entry or {}).get("text") or "")
        text = raw_text.lower()
        eid = open_event_ids.get(cid)
        actual_commitments.append(
            {"text": text, "raw_text": raw_text, "cid": cid[:8], "eid": eid}
        )

    def _core_claim_phrase(s: str) -> str:
        """Extract core phrase after 'committed to' deterministically.

        Falls back to full string if pattern not present.
        """
        low = s.lower().strip()
        key = "committed to"
        if key in low:
            rest = low[low.find(key) + len(key) :].strip()
            # If starts with a quote, extract inside the quote deterministically
            if rest.startswith('"') or rest.startswith("'"):
                q = rest[0]
                content = []
                for ch in rest[1:]:
                    if ch == q:
                        break
                    content.append(ch)
                inner = "".join(content).strip()
                if inner:
                    return inner
            # Cut at punctuation or quote/markdown markers
            out = []
            for ch in rest:
                if ch in ".,;!?\"'*_`:|→":
                    break
                out.append(ch)
            core = "".join(out).strip()
            return core or low
        return low

    # Verify each claim
    for claim in claimed_commitments:
        claim = claim.strip()
        if len(claim) < 2:  # Skip very short claims
            continue

        claim_lower = claim.lower()
        numeric_token: str | None = None
        if claim.isdigit():
            numeric_token = claim
        elif "event" in claim_lower and "id" in claim_lower:
            tokens = (
                claim_lower.replace(":", " ")
                .replace(",", " ")
                .replace("-", " ")
                .split()
            )
            for token in tokens:
                if token.isdigit():
                    numeric_token = token
                    break

        # Check if claim is an event ID (numeric)
        found = False
        if numeric_token is not None:
            # Claim is an event ID - verify it exists and is a commitment_open
            claimed_eid = int(numeric_token)
            for actual in actual_commitments:
                if actual.get("eid") == claimed_eid:
                    found = True
                    break

            if not found:
                # Show user-friendly message
                print("😕 Hmm, that doesn't match the ledger...")
                import time

                time.sleep(0.8)  # Let user see the message

                sample_ids = [
                    c.get("eid")
                    for c in actual_commitments[:5]
                    if c.get("eid") is not None
                ]
                logger.warning(
                    f"⚠️  Commitment hallucination detected: "
                    f"LLM claimed event ID {claimed_eid} is a commitment, but it's not in the ledger. "
                    f"Actual open commitment event IDs: {sample_ids}"
                )

                # Build correction message for next turn
                correction = (
                    f"[VALIDATOR_CORRECTION] You referenced commitment event ID {claimed_eid}, "
                    f"but the ledger shows no such open commitment. "
                    f"Actual open commitment event IDs: {sample_ids[:5]}. "
                    f"Please verify against the ledger before citing commitments."
                )

                try:
                    available_texts = [
                        c.get("raw_text")
                        for c in actual_commitments
                        if c.get("raw_text")
                    ]
                    _io.append_commitment_hallucination(
                        eventlog,
                        claims=[f"event_id:{claimed_eid}"],
                        available_eids=sample_ids,
                        available_texts=available_texts,
                        claim_type="event_id",
                    )
                except Exception:
                    logger.debug(
                        "Failed to append commitment hallucination event",
                        exc_info=True,
                    )
                return (True, correction)
        else:
            # Claim is text — semantic match against actual open commitment raw_text
            # Use graduated severity thresholds
            core = _core_claim_phrase(claim)
            emb_claim = compute_embedding(core)
            best_sim = 0.0
            best_match = None
            for actual in actual_commitments:
                raw = actual.get("raw_text") or ""
                emb_raw = compute_embedding(raw)
                sim = cosine_similarity(emb_claim, emb_raw)
                if sim > best_sim:
                    best_sim = sim
                    best_match = actual
                if sim >= 0.70:
                    found = True
                    break

            if not found:
                # Show user-friendly message
                print("😕 Hmm, that doesn't match the ledger...")
                import time

                time.sleep(0.8)  # Let user see the message

                # Graduated severity based on best similarity score
                if best_sim >= 0.60:
                    logger.info(
                        f"ℹ️  Commitment reference is paraphrased (sim={best_sim:.2f}): "
                        f"claimed '{claim[:50]}' vs actual '{best_match.get('raw_text', '')[:50]}'"
                    )
                elif best_sim >= 0.40:
                    logger.warning(
                        f"⚠️  Commitment reference has semantic drift (sim={best_sim:.2f}): "
                        f"claimed '{claim[:50]}' vs closest '{best_match.get('raw_text', '')[:50]}'"
                    )
                else:
                    logger.warning(
                        f"⚠️  Commitment hallucination detected (sim={best_sim:.2f}): "
                        f"LLM claimed commitment about '{claim}' but no matching commitment_open found in ledger. "
                        f"Actual open commitments: {[c['text'][:50] for c in actual_commitments[:3]]}"
                    )

                # Build correction message with graduated feedback
                if best_sim >= 0.60:
                    correction = (
                        f"[VALIDATOR_NOTE] Your commitment reference appears to be a paraphrase. "
                        f"You said: '{claim[:80]}'. "
                        f"The ledger shows: '{best_match.get('raw_text', '')[:80]}'. "
                        f"Consider using more precise language or event IDs."
                    )
                else:
                    correction = (
                        f"[VALIDATOR_CORRECTION] You referenced a commitment about '{claim[:80]}', "
                        f"but no matching open commitment was found (best similarity: {best_sim:.2f}). "
                        f"Actual open commitments: {[c['text'][:60] for c in actual_commitments[:3]]}. "
                        f"Please verify against the ledger before citing commitments."
                    )

                try:
                    available_texts = [
                        c.get("raw_text")
                        for c in actual_commitments
                        if c.get("raw_text")
                    ]
                    available_eids = [
                        c.get("eid")
                        for c in actual_commitments
                        if c.get("eid") is not None
                    ]
                    _io.append_commitment_hallucination(
                        eventlog,
                        claims=[_core_claim_phrase(claim_lower)],
                        available_eids=available_eids,
                        available_texts=available_texts,
                        claim_type="text",
                    )
                except Exception:
                    logger.debug(
                        "Failed to append commitment hallucination event", exc_info=True
                    )

                # Only block response for true hallucinations (sim < 0.60)
                if best_sim < 0.60:
                    return (True, correction)
                else:
                    # Paraphrase - allow but provide feedback
                    return (False, correction)

    return (False, None)


def verify_commitment_status(reply: str, eventlog: EventLog) -> tuple[bool, list[str]]:
    """Verify that commitment status claims (open/closed) match ledger reality.

    Catches semantic hallucinations where the model claims a commitment is closed
    when it's actually still open, or vice versa.

    Returns:
        (is_valid, mismatched_cids): True if all status claims are accurate.
    """
    from pmm.storage.projection import build_self_model

    # Build current state to see what's actually open
    events = eventlog.read_all()
    model = build_self_model(events, eventlog=eventlog)
    open_cids = set(model.get("commitments", {}).get("open", {}).keys())

    # Extract closed commitment claims using deterministic parser
    claimed_closed_cids = extract_closed_commitment_claims(reply)

    mismatched = []
    for cid_prefix in claimed_closed_cids:
        # Check if any open CID starts with this prefix
        for open_cid in open_cids:
            if open_cid.startswith(cid_prefix):
                mismatched.append(f"{cid_prefix} (claimed closed, actually open)")
                break

    return len(mismatched) == 0, mismatched


def verify_event_ids(reply: str, eventlog: EventLog) -> tuple[bool, list[int]]:
    """Verify that event ID references in LLM response exist in the ledger.

    This validator catches hallucinated event IDs (e.g., "event 7892" when
    only events 1-3000 exist). It scans for numeric patterns that look like
    event IDs and cross-checks against the ledger.

    Uses adaptive two-tier validation that scales with ledger size:
    1. Fast path: check recent window (scales with ledger size, min 1K, max 10K)
    2. Slow path: full ledger scan only if needed (for historical references)

    Args:
        reply: The LLM's response text
        eventlog: EventLog instance to query for real IDs

    Returns:
        (is_valid, fake_ids): True if all IDs are real, False otherwise.
                              fake_ids lists any hallucinated IDs found.

    Side effects:
        None (pure validation function)
    """
    # Use deterministic parser instead of regex
    mentioned_ids = set(extract_event_ids(reply))

    # Also extract from commitment format (e.g., "562:bab3a368")
    parse_commitment_refs(reply)
    # Commitment refs include the event ID prefix, extract those too
    for token in reply.split():
        if ":" in token:
            parts = token.split(":")
            if len(parts) == 2 and parts[0].isdigit() and 2 <= len(parts[0]) <= 5:
                try:
                    mentioned_ids.add(int(parts[0]))
                except ValueError:
                    continue

    if not mentioned_ids:
        return True, []

    # Determine adaptive window size based on ledger scale
    # For small ledgers (<10K): use 40% of ledger (min 1K)
    # For large ledgers (>10K): cap at 10K to maintain performance
    try:
        # Quick peek at ledger size via tail
        tail_sample = eventlog.read_tail(limit=1)
        if tail_sample:
            max_event_id = tail_sample[-1].get("id", 1000)
            # Adaptive window: 40% of ledger, bounded [1K, 10K]
            window_size = max(1000, min(10000, int(max_event_id * 0.4)))
        else:
            window_size = 1000
    except Exception:
        window_size = 1000

    # Tier 1: Fast check (recent events - adaptive window)
    try:
        recent_events = eventlog.read_tail(limit=window_size)
        recent_ids = {e["id"] for e in recent_events}
    except Exception:
        # If query fails, assume valid to avoid false positives
        logger.warning("Failed to query recent events for ID validation")
        return True, []

    # Check against recent window first
    potential_fakes = [eid for eid in mentioned_ids if eid not in recent_ids]

    # Tier 2: Full validation only if needed (historical references)
    if potential_fakes:
        try:
            all_events = eventlog.read_all()
            all_ids = {e["id"] for e in all_events}
            fake_ids = sorted([eid for eid in potential_fakes if eid not in all_ids])
        except Exception:
            logger.warning("Failed to query full ledger for ID validation")
            return True, []
    else:
        fake_ids = []

    return len(fake_ids) == 0, fake_ids


def verify_commitment_count_claims(reply: str, actual_open_count: int) -> bool:
    """Verify that commitment count claims match ledger reality.

    Catches claims like "I have no active commitments" when commitments are open.
    Only fires on affirmative factual claims, not questions or conditionals.

    Args:
        reply: The LLM's response text
        actual_open_count: Actual count of open commitments from ledger

    Returns:
        True if hallucination detected, False otherwise
    """
    if actual_open_count == 0:
        return False  # No mismatch possible if truly zero

    # Match only affirmative factual claims about zero commitments
    claim = reply.strip().lower()
    bad_phrases = [
        "i have no active commitments",
        "i have no open commitments",
        "there are no open commitments",
        "open commitments: 0",
        "no active commitments",
        "0 open commitments",
        "zero open commitments",
        "zero active commitments",
    ]

    for phrase in bad_phrases:
        if phrase in claim:
            logger.warning(
                f"⚠️  Commitment count hallucination: "
                f"LLM claimed zero commitments, but ledger shows {actual_open_count} open"
            )
            print("😕 Hmm, that doesn't match the ledger...")
            import time

            time.sleep(0.8)
            return True

    return False


__all__ = [
    "verify_commitment_claims",
    "verify_commitment_status",
    "verify_commitment_count_claims",
    "verify_event_ids",
    "verify_event_existence_claims",
]
