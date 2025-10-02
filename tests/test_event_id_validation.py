"""Test event ID hallucination detection."""

import tempfile
import os

from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import _verify_event_ids


def test_verify_event_ids_valid():
    """Test that real event IDs pass validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(path=db_path)

        # Create some real events
        eid1 = log.append(kind="test", content="event1", meta={})
        eid2 = log.append(kind="test", content="event2", meta={})

        # Reply references real IDs
        reply = f"I see event {eid1} and event {eid2} in the ledger."

        is_valid, fake_ids = _verify_event_ids(reply, log)

        assert is_valid is True
        assert fake_ids == []


def test_verify_event_ids_hallucinated():
    """Test that fake event IDs are detected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(path=db_path)

        # Create some real events
        log.append(kind="test", content="event1", meta={})
        log.append(kind="test", content="event2", meta={})

        # Reply references non-existent IDs
        reply = "I see event 7892 and event 9876 in the ledger."

        is_valid, fake_ids = _verify_event_ids(reply, log)

        assert is_valid is False
        assert 7892 in fake_ids
        assert 9876 in fake_ids


def test_verify_event_ids_commitment_format():
    """Test that commitment format IDs (e.g., 562:bab3a368) are validated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(path=db_path)

        # Create real event at ID 562
        for _ in range(562):
            log.append(kind="test", content="filler", meta={})

        # Reply uses commitment format with real ID
        reply = "Commitment 562:bab3a368 is open."

        is_valid, fake_ids = _verify_event_ids(reply, log)

        assert is_valid is True
        assert fake_ids == []

        # Reply uses commitment format with fake ID
        reply_fake = "Commitment 9999:deadbeef is open."

        is_valid_fake, fake_ids_fake = _verify_event_ids(reply_fake, log)

        assert is_valid_fake is False
        assert 9999 in fake_ids_fake


def test_verify_event_ids_no_mentions():
    """Test that replies without event IDs pass validation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        log = EventLog(path=db_path)

        log.append(kind="test", content="event1", meta={})

        # Reply doesn't mention any IDs
        reply = "The system is functioning normally."

        is_valid, fake_ids = _verify_event_ids(reply, log)

        assert is_valid is True
        assert fake_ids == []
