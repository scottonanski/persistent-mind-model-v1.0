"""Anti-hallucination validators (Stage 4 extraction).

Extracts commitment and event ID validation functions from monolithic loop.py.
All behavior preserved exactly as-is per CONTRIBUTING.md.
"""

from __future__ import annotations

import logging
from typing import Any

from pmm.storage.eventlog import EventLog
from pmm.utils.parsers import (
    extract_closed_commitment_claims,
    extract_commitment_claims,
    extract_event_ids,
    parse_commitment_refs,
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


def verify_commitment_claims(reply: str, eventlog: EventLog) -> bool:
    """Verify that commitment claims in LLM response match ledger reality.

    This is a post-response validator that catches commitment hallucinations.
    It only runs if the response mentions "commit" to minimize overhead.

    Args:
        reply: The LLM's response text
        eventlog: Ledger interface for querying commitment state

    Returns:
        True if hallucination detected, False otherwise

    Side effects:
        Logs warnings if mismatches are detected
        Prints user-friendly emoji message when hallucination found
    """
    # Lazy validation: only check if response mentions commitments
    reply_lower = reply.lower()
    if "commit" not in reply_lower:
        return

    # Extract commitment claims from response using deterministic parser
    claimed_commitments = extract_commitment_claims(reply)

    if not claimed_commitments:
        return False  # No specific claims to verify

    # Build current self-model to determine which commitments remain open
    from pmm.storage.projection import build_self_model

    try:
        events = eventlog.read_all()
    except Exception:
        logger.warning("Failed to read ledger for commitment validation", exc_info=True)
        return False

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
        text = str((entry or {}).get("text") or "").lower()
        eid = open_event_ids.get(cid)
        actual_commitments.append({"text": text, "cid": cid[:8], "eid": eid})

    # Verify each claim
    for claim in claimed_commitments:
        claim = claim.strip()
        if len(claim) < 2:  # Skip very short claims
            continue

        # Check if claim is an event ID (numeric)
        found = False
        if claim.isdigit():
            # Claim is an event ID - verify it exists and is a commitment_open
            claimed_eid = int(claim)
            for actual in actual_commitments:
                if actual.get("eid") == claimed_eid:
                    found = True
                    break

            if not found:
                # Show user-friendly message
                print("😕 Hmm, that doesn't match the ledger...")
                import time

                time.sleep(0.8)  # Let user see the message

                logger.warning(
                    f"⚠️  Commitment hallucination detected: "
                    f"LLM claimed event ID {claimed_eid} is a commitment, but it's not in the ledger. "
                    f"Actual open commitment event IDs: {[c.get('eid') for c in actual_commitments[:5] if c.get('eid')]}"
                )
                return True
        else:
            # Claim is text - check if it matches any actual commitment text
            for actual in actual_commitments:
                if claim in actual["text"] or actual["text"].find(claim) >= 0:
                    found = True
                    break

            if not found:
                # Show user-friendly message
                print("😕 Hmm, that doesn't match the ledger...")
                import time

                time.sleep(0.8)  # Let user see the message

                logger.warning(
                    f"⚠️  Commitment hallucination detected: "
                    f"LLM claimed commitment about '{claim}' but no matching commitment_open found in ledger. "
                    f"Actual open commitments: {[c['text'][:50] for c in actual_commitments[:3]]}"
                )
                return True

    return False


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
