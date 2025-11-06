from __future__ import annotations

import pytest

from pmm_v2.core.schemas import (
    generate_internal_cid,
    hash_payload,
    validate_event,
)


def _event(kind: str, meta: dict) -> dict:
    return {"kind": kind, "meta": meta}


def test_internal_commitment_requires_goal():
    meta = {"cid": "mc_000123", "origin": "autonomy_kernel"}
    with pytest.raises(ValueError):
        validate_event(_event("commitment_open", meta))


def test_external_commitment_rejects_goal():
    meta = {"cid": "user_abc", "origin": "assistant", "goal": "not allowed"}
    with pytest.raises(ValueError):
        validate_event(_event("commitment_close", meta))


def test_hash_includes_origin_and_goal():
    meta = {
        "goal": "monitor_rsm_evolution",
        "cid": "mc_000045",
        "origin": "autonomy_kernel",
    }
    payload_a = hash_payload("commitment_open", meta)
    meta_permuted = {
        "origin": "autonomy_kernel",
        "cid": "mc_000045",
        "goal": "monitor_rsm_evolution",
    }
    payload_b = hash_payload("commitment_open", meta_permuted)
    assert payload_a == payload_b
    assert '"origin":"autonomy_kernel"' in payload_a
    assert '"goal":"monitor_rsm_evolution"' in payload_a


def test_internal_cid_format():
    assert generate_internal_cid(7) == "mc_000007"
    assert generate_internal_cid(123456) == "mc_123456"
    with pytest.raises(ValueError):
        generate_internal_cid(-1)


def test_duplicate_internal_commitment_idempotent():
    meta_one = {
        "cid": "mc_000888",
        "origin": "autonomy_kernel",
        "goal": "ensure idempotency",
    }
    meta_two = {
        "goal": "ensure idempotency",
        "origin": "autonomy_kernel",
        "cid": "mc_000888",
    }
    payloads = {
        hash_payload("commitment_open", meta_one),
        hash_payload("commitment_open", meta_two),
    }
    assert len(payloads) == 1
