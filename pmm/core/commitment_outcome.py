# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Governed commitment outcome and later-review relationship predicates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable, Dict, Mapping, Optional

from .semantic_extractor import extract_closures

OUTCOME_PROTOCOL_V1 = "commitment_outcome.v1"
REVIEW_PROTOCOL_V1 = "commitment_outcome_review.v1"
OUTCOME_CANDIDATE_PREFIX = "COMMITMENT_OUTCOME:"
REVIEW_CANDIDATE_PREFIX = "COMMITMENT_REVIEW:"
OUTCOME_VALIDATOR_SOURCE = "commitment_outcome_validator"
REVIEW_VALIDATOR_SOURCE = "commitment_outcome_review_validator"

OUTCOME_CONTENT_KEYS = frozenset({"observation", "evidence_event_ids"})
OUTCOME_META_KEYS = frozenset(
    {
        "protocol",
        "source",
        "cid",
        "open_event_id",
        "close_event_id",
        "origin_event_id",
    }
)
REVIEW_CONTENT_KEYS = frozenset({"interpretation"})
REVIEW_META_KEYS = frozenset(
    {
        "protocol",
        "source",
        "cid",
        "open_event_id",
        "outcome_event_id",
        "origin_event_id",
    }
)

GetEvent = Callable[[int], Optional[Dict[str, Any]]]
IsManagedAssistant = Callable[[int], bool]
IsRegisteredRelationship = Callable[[int], bool]


@dataclass(frozen=True)
class CommitmentRelationshipValidation:
    ok: bool
    code: str
    message: str
    cid: str = ""
    open_event_id: Optional[int] = None
    close_event_id: Optional[int] = None
    outcome_event_id: Optional[int] = None
    origin_event_id: Optional[int] = None
    observation: str = ""
    interpretation: str = ""
    evidence_event_ids: tuple[int, ...] = ()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _canonical_nonempty(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip() and value == value.strip():
        return value
    return None


def _fail(
    code: str,
    message: str,
    *,
    cid: str = "",
    open_event_id: Optional[int] = None,
    close_event_id: Optional[int] = None,
    outcome_event_id: Optional[int] = None,
    origin_event_id: Optional[int] = None,
) -> CommitmentRelationshipValidation:
    return CommitmentRelationshipValidation(
        False,
        code,
        message,
        cid=cid,
        open_event_id=open_event_id,
        close_event_id=close_event_id,
        outcome_event_id=outcome_event_id,
        origin_event_id=origin_event_id,
    )


def parse_prefixed_candidates(text: str, prefix: str) -> list[tuple[str, Any]]:
    """Return raw and parsed payloads for every exact-prefix candidate line."""

    candidates: list[tuple[str, Any]] = []
    for line in str(text or "").splitlines():
        if not line.startswith(prefix):
            continue
        raw = line[len(prefix) :]
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            parsed = None
        candidates.append((raw, parsed))
    return candidates


def strip_commitment_relationship_candidates(text: str) -> str:
    """Remove v1 control lines before generic semantic/identity interpretation."""

    return "\n".join(
        line
        for line in str(text or "").splitlines()
        if not line.startswith((OUTCOME_CANDIDATE_PREFIX, REVIEW_CANDIDATE_PREFIX))
    )


def stable_attempted_value(value: Any) -> Any:
    """Return deterministic JSON-safe failure material for hostile inputs."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): stable_attempted_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [stable_attempted_value(item) for item in value]
    return {"unsupported_type": f"{type(value).__module__}.{type(value).__qualname__}"}


def attempted_relationship_digest(
    *, kind: str, content: Any, meta: Mapping[str, Any]
) -> str:
    payload: Dict[str, Any] = {
        "kind": kind,
        "content": stable_attempted_value(content),
        "meta": stable_attempted_value(dict(meta)),
    }
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            payload["content"] = stable_attempted_value(parsed)
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def canonical_outcome_content(
    *, observation: str, evidence_event_ids: list[int] | tuple[int, ...]
) -> str:
    return _canonical_json(
        {
            "evidence_event_ids": list(evidence_event_ids),
            "observation": observation,
        }
    )


def canonical_review_content(*, interpretation: str) -> str:
    return _canonical_json({"interpretation": interpretation})


def is_outcome_review_protocol(event: Mapping[str, Any] | None) -> bool:
    """True for protocol-shaped reviews, including invalid preserved rows."""

    if not isinstance(event, Mapping) or event.get("kind") != "reflection":
        return False
    meta = event.get("meta") or {}
    return isinstance(meta, Mapping) and meta.get("protocol") == REVIEW_PROTOCOL_V1


def is_commitment_relationship_protocol(event: Mapping[str, Any] | None) -> bool:
    """True for either v1 relationship shape, including invalid preserved rows."""

    if not isinstance(event, Mapping):
        return False
    meta = event.get("meta") or {}
    if not isinstance(meta, Mapping):
        return False
    return (
        event.get("kind") == "outcome_observation"
        and meta.get("protocol") == OUTCOME_PROTOCOL_V1
    ) or (
        event.get("kind") == "reflection" and meta.get("protocol") == REVIEW_PROTOCOL_V1
    )


def _assistant_emitted_candidate(
    origin: Mapping[str, Any] | None,
    *,
    get_event: GetEvent,
    origin_event_id: int,
    before_event_id: Optional[int],
    prefix: str,
    expected: Mapping[str, Any],
    is_managed_assistant: IsManagedAssistant,
) -> bool:
    if not isinstance(origin, Mapping) or origin.get("kind") != "assistant_message":
        return False
    loaded_id = _positive_int(origin.get("id"))
    if loaded_id != origin_event_id:
        return False
    if not is_managed_assistant(origin_event_id):
        return False
    origin_meta = origin.get("meta") or {}
    if not isinstance(origin_meta, Mapping):
        return False
    user_event_id = _positive_int(origin_meta.get("about_event"))
    if (
        origin_meta.get("turn_protocol") != "terminal_outcome.v1"
        or user_event_id is None
        or user_event_id >= origin_event_id
    ):
        return False
    user_event = get_event(user_event_id)
    user_meta = (user_event or {}).get("meta") or {}
    if (
        not isinstance(user_event, Mapping)
        or user_event.get("kind") != "user_message"
        or not isinstance(user_meta, Mapping)
        or user_meta.get("role") != "user"
        or user_meta.get("turn_protocol") != "terminal_outcome.v1"
    ):
        return False
    if before_event_id is not None and origin_event_id >= before_event_id:
        return False
    content = origin.get("content")
    if not isinstance(content, str):
        return False
    return any(
        isinstance(parsed, dict) and parsed == dict(expected)
        for _raw, parsed in parse_prefixed_candidates(content, prefix)
    )


def _authoritative_close_matches(
    close: Mapping[str, Any] | None,
    *,
    close_event_id: int,
    open_event_id: int,
    cid: str,
    get_event: GetEvent,
) -> bool:
    if not isinstance(close, Mapping) or close.get("kind") != "commitment_close":
        return False
    if _positive_int(close.get("id")) != close_event_id:
        return False
    meta = close.get("meta") or {}
    if (
        not isinstance(meta, Mapping)
        or meta.get("open_event_id") != open_event_id
        or meta.get("cid") != cid
    ):
        return False
    source = _canonical_nonempty(meta.get("source"))
    if source is None:
        return False
    if source != "assistant":
        return "origin_event_id" not in meta
    origin_event_id = _positive_int(meta.get("origin_event_id"))
    if origin_event_id is None or origin_event_id >= close_event_id:
        return False
    origin = get_event(origin_event_id)
    if not isinstance(origin, Mapping) or origin.get("kind") != "assistant_message":
        return False
    if origin_event_id <= open_event_id:
        open_event = get_event(open_event_id) or {}
        if (open_event.get("meta") or {}).get("origin_event_id") != origin_event_id:
            return False
    content = origin.get("content")
    return isinstance(content, str) and cid in extract_closures(content.splitlines())


def validate_outcome_payload(
    content: str,
    meta: Mapping[str, Any],
    get_event: GetEvent,
    *,
    outcome_id: Optional[int] = None,
    is_managed_assistant: IsManagedAssistant,
) -> CommitmentRelationshipValidation:
    if not isinstance(content, str) or not isinstance(meta, Mapping):
        return _fail(
            "INVALID_OUTCOME_STRUCTURE",
            "outcome requires string content and object meta",
        )
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return _fail("INVALID_OUTCOME_STRUCTURE", "outcome content must be JSON")
    if not isinstance(data, dict) or set(data) != OUTCOME_CONTENT_KEYS:
        return _fail(
            "INVALID_OUTCOME_STRUCTURE",
            "outcome content must contain only observation and evidence_event_ids",
        )
    if set(meta) != OUTCOME_META_KEYS:
        return _fail(
            "INVALID_OUTCOME_STRUCTURE",
            "outcome meta must contain exactly the v1 relationship fields",
        )
    if meta.get("protocol") != OUTCOME_PROTOCOL_V1 or meta.get("source") != "assistant":
        return _fail(
            "INVALID_OUTCOME_PRODUCER",
            "outcome requires commitment_outcome.v1 and assistant source",
        )
    cid = _canonical_nonempty(meta.get("cid"))
    observation = _canonical_nonempty(data.get("observation"))
    open_event_id = _positive_int(meta.get("open_event_id"))
    close_event_id = _positive_int(meta.get("close_event_id"))
    origin_event_id = _positive_int(meta.get("origin_event_id"))
    if (
        cid is None
        or observation is None
        or None
        in {
            open_event_id,
            close_event_id,
            origin_event_id,
        }
    ):
        return _fail(
            "INVALID_OUTCOME_STRUCTURE",
            "outcome requires canonical text, cid, and positive reference ids",
            cid=str(meta.get("cid") or ""),
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    evidence = data.get("evidence_event_ids")
    if not isinstance(evidence, list) or not evidence:
        return _fail(
            "INVALID_OUTCOME_EVIDENCE",
            "outcome evidence_event_ids must be a non-empty list",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    evidence_ids = tuple(_positive_int(item) for item in evidence)
    if any(item is None for item in evidence_ids) or len(set(evidence_ids)) != len(
        evidence_ids
    ):
        return _fail(
            "INVALID_OUTCOME_EVIDENCE",
            "outcome evidence ids must be unique positive integers",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    typed_evidence_ids = tuple(int(item) for item in evidence_ids if item is not None)
    if not (open_event_id < close_event_id):
        return _fail(
            "INVALID_OUTCOME_ORDER",
            "outcome requires open_event_id < close_event_id",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    if outcome_id is not None and not (
        close_event_id < outcome_id
        and origin_event_id < outcome_id
        and all(event_id < outcome_id for event_id in typed_evidence_ids)
    ):
        return _fail(
            "INVALID_OUTCOME_ORDER",
            "outcome references must precede the outcome event",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    open_event = get_event(open_event_id)
    close_event = get_event(close_event_id)
    if (
        not isinstance(open_event, Mapping)
        or open_event.get("kind") != "commitment_open"
    ):
        return _fail(
            "INVALID_OUTCOME_EPISODE",
            "open_event_id must identify a commitment_open",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    if (open_event.get("meta") or {}).get("cid") != cid:
        return _fail(
            "OUTCOME_CID_MISMATCH",
            "outcome cid must match the exact open event",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    if not _authoritative_close_matches(
        close_event,
        close_event_id=close_event_id,
        open_event_id=open_event_id,
        cid=cid,
        get_event=get_event,
    ):
        return _fail(
            "INVALID_OUTCOME_CLOSE",
            "close_event_id must be the authoritative close for the exact episode",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    if any(
        event_id <= open_event_id or get_event(event_id) is None
        for event_id in typed_evidence_ids
    ):
        return _fail(
            "INVALID_OUTCOME_EVIDENCE",
            "outcome evidence must identify existing events after the open",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    expected_candidate = {
        "cid": cid,
        "close_event_id": close_event_id,
        "evidence_event_ids": list(typed_evidence_ids),
        "observation": observation,
        "open_event_id": open_event_id,
    }
    if not _assistant_emitted_candidate(
        get_event(origin_event_id),
        get_event=get_event,
        origin_event_id=origin_event_id,
        before_event_id=outcome_id,
        prefix=OUTCOME_CANDIDATE_PREFIX,
        expected=expected_candidate,
        is_managed_assistant=is_managed_assistant,
    ):
        return _fail(
            "INVALID_OUTCOME_PRODUCER",
            "origin_event_id must identify the assistant that emitted the exact outcome candidate",
            cid=cid,
            open_event_id=open_event_id,
            close_event_id=close_event_id,
            origin_event_id=origin_event_id,
        )
    return CommitmentRelationshipValidation(
        True,
        "VALID",
        "commitment outcome valid",
        cid=cid,
        open_event_id=open_event_id,
        close_event_id=close_event_id,
        origin_event_id=origin_event_id,
        observation=observation,
        evidence_event_ids=typed_evidence_ids,
    )


def is_v1_authoritative_outcome(
    event: Mapping[str, Any],
    get_event: GetEvent,
    is_managed_assistant: IsManagedAssistant,
    is_registered_outcome: IsRegisteredRelationship,
) -> bool:
    if event.get("kind") != "outcome_observation":
        return False
    meta = event.get("meta") or {}
    if not isinstance(meta, Mapping) or meta.get("protocol") != OUTCOME_PROTOCOL_V1:
        return False
    content = event.get("content")
    if not isinstance(content, str):
        return False
    event_id = _positive_int(event.get("id"))
    if event_id is None or not is_registered_outcome(event_id):
        return False
    return validate_outcome_payload(
        content,
        meta,
        get_event,
        outcome_id=event_id,
        is_managed_assistant=is_managed_assistant,
    ).ok


def validate_review_payload(
    content: str,
    meta: Mapping[str, Any],
    get_event: GetEvent,
    *,
    review_id: Optional[int] = None,
    is_managed_assistant: IsManagedAssistant,
    is_registered_outcome: IsRegisteredRelationship,
) -> CommitmentRelationshipValidation:
    if not isinstance(content, str) or not isinstance(meta, Mapping):
        return _fail(
            "INVALID_REVIEW_STRUCTURE", "review requires string content and object meta"
        )
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return _fail("INVALID_REVIEW_STRUCTURE", "review content must be JSON")
    if not isinstance(data, dict) or set(data) != REVIEW_CONTENT_KEYS:
        return _fail(
            "INVALID_REVIEW_STRUCTURE",
            "review content must contain only interpretation",
        )
    if set(meta) != REVIEW_META_KEYS:
        return _fail(
            "INVALID_REVIEW_STRUCTURE",
            "review meta must contain exactly the v1 relationship fields",
        )
    if meta.get("protocol") != REVIEW_PROTOCOL_V1 or meta.get("source") != "assistant":
        return _fail(
            "INVALID_REVIEW_PRODUCER",
            "review requires commitment_outcome_review.v1 and assistant source",
        )
    cid = _canonical_nonempty(meta.get("cid"))
    interpretation = _canonical_nonempty(data.get("interpretation"))
    open_event_id = _positive_int(meta.get("open_event_id"))
    outcome_event_id = _positive_int(meta.get("outcome_event_id"))
    origin_event_id = _positive_int(meta.get("origin_event_id"))
    if (
        cid is None
        or interpretation is None
        or None
        in {
            open_event_id,
            outcome_event_id,
            origin_event_id,
        }
    ):
        return _fail(
            "INVALID_REVIEW_STRUCTURE",
            "review requires canonical text, cid, and positive reference ids",
            cid=str(meta.get("cid") or ""),
            open_event_id=open_event_id,
            outcome_event_id=outcome_event_id,
            origin_event_id=origin_event_id,
        )
    if not (outcome_event_id < origin_event_id):
        return _fail(
            "INVALID_REVIEW_ORDER",
            "review assistant candidate must follow the outcome",
            cid=cid,
            open_event_id=open_event_id,
            outcome_event_id=outcome_event_id,
            origin_event_id=origin_event_id,
        )
    if review_id is not None and not (origin_event_id < review_id):
        return _fail(
            "INVALID_REVIEW_ORDER",
            "review origin must precede the review event",
            cid=cid,
            open_event_id=open_event_id,
            outcome_event_id=outcome_event_id,
            origin_event_id=origin_event_id,
        )
    outcome = get_event(outcome_event_id)
    if not isinstance(outcome, Mapping) or not is_v1_authoritative_outcome(
        outcome, get_event, is_managed_assistant, is_registered_outcome
    ):
        return _fail(
            "INVALID_REVIEW_OUTCOME",
            "outcome_event_id must identify an authoritative v1 outcome",
            cid=cid,
            open_event_id=open_event_id,
            outcome_event_id=outcome_event_id,
            origin_event_id=origin_event_id,
        )
    outcome_meta = outcome.get("meta") or {}
    if (
        outcome_meta.get("cid") != cid
        or outcome_meta.get("open_event_id") != open_event_id
    ):
        return _fail(
            "REVIEW_EPISODE_MISMATCH",
            "review cid and open_event_id must match the exact outcome episode",
            cid=cid,
            open_event_id=open_event_id,
            outcome_event_id=outcome_event_id,
            origin_event_id=origin_event_id,
        )
    expected_candidate = {
        "cid": cid,
        "interpretation": interpretation,
        "open_event_id": open_event_id,
        "outcome_event_id": outcome_event_id,
    }
    if not _assistant_emitted_candidate(
        get_event(origin_event_id),
        get_event=get_event,
        origin_event_id=origin_event_id,
        before_event_id=review_id,
        prefix=REVIEW_CANDIDATE_PREFIX,
        expected=expected_candidate,
        is_managed_assistant=is_managed_assistant,
    ):
        return _fail(
            "INVALID_REVIEW_PRODUCER",
            "origin_event_id must identify the assistant that emitted the exact review candidate",
            cid=cid,
            open_event_id=open_event_id,
            outcome_event_id=outcome_event_id,
            origin_event_id=origin_event_id,
        )
    return CommitmentRelationshipValidation(
        True,
        "VALID",
        "commitment outcome review valid",
        cid=cid,
        open_event_id=open_event_id,
        outcome_event_id=outcome_event_id,
        origin_event_id=origin_event_id,
        interpretation=interpretation,
    )


def is_v1_authoritative_review(
    event: Mapping[str, Any],
    get_event: GetEvent,
    is_managed_assistant: IsManagedAssistant,
    is_registered_outcome: IsRegisteredRelationship,
    is_registered_review: IsRegisteredRelationship,
) -> bool:
    if event.get("kind") != "reflection":
        return False
    meta = event.get("meta") or {}
    if not isinstance(meta, Mapping) or meta.get("protocol") != REVIEW_PROTOCOL_V1:
        return False
    content = event.get("content")
    if not isinstance(content, str):
        return False
    event_id = _positive_int(event.get("id"))
    if event_id is None or not is_registered_review(event_id):
        return False
    return validate_review_payload(
        content,
        meta,
        get_event,
        review_id=event_id,
        is_managed_assistant=is_managed_assistant,
        is_registered_outcome=is_registered_outcome,
    ).ok
