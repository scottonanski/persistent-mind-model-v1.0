# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.core.ledger_mirror import LedgerMirror
from pmm.core.schemas import Claim
from pmm.core.validators import validate_claim


def test_validate_claims_basic():
    log = EventLog(":memory:")
    mirror = LedgerMirror(log)

    # Seed some events
    e1 = log.append(kind="user_message", content="hi", meta={})
    e2 = log.append(kind="assistant_message", content="hello", meta={})

    ok, msg = validate_claim(
        Claim(type="event_existence", data={"id": e1}), log, mirror
    )
    assert ok and msg == "event exists"

    ok, msg = validate_claim(
        Claim(type="event_existence", data={"id": 99999}), log, mirror
    )
    assert not ok and msg == "no such event"

    # Commitment open then status true
    log.append(kind="commitment_open", content="c", meta={"cid": "abcd", "text": "x"})
    ok, msg = validate_claim(
        Claim(type="commitment_status", data={"cid": "abcd", "open": True}), log, mirror
    )
    assert ok and msg == "commitment ok"

    # Close and expect false for open=True
    log.append(kind="commitment_close", content="c", meta={"cid": "abcd"})
    ok, msg = validate_claim(
        Claim(type="commitment_status", data={"cid": "abcd", "open": True}), log, mirror
    )
    assert not ok and msg == "commitment mismatch"

    # Reference claim
    ok, msg = validate_claim(Claim(type="reference", data={"id": e2}), log, mirror)
    assert ok and msg == "reference valid"

    ok, msg = validate_claim(Claim(type="reference", data={"id": 424242}), log, mirror)
    assert not ok and msg == "invalid reference"
