# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_eventlog_ctl.py
"""Tests for EventLog integration with CTL event kinds."""


from pmm.core.event_log import EventLog
from pmm.core.concept_schemas import (
    create_concept_define_payload,
    create_concept_alias_payload,
    create_concept_bind_event_payload,
    create_concept_relate_payload,
    create_concept_state_snapshot_payload,
)


class TestEventLogCTL:
    def test_eventlog_accepts_concept_define(self):
        log = EventLog()
        content, meta = create_concept_define_payload(
            token="identity.Echo",
            concept_kind="identity",
            definition="Primary identity facet",
        )

        event_id = log.append(kind="concept_define", content=content, meta=meta)
        assert event_id > 0

        event = log.get(event_id)
        assert event["kind"] == "concept_define"
        assert event["content"] == content
        assert event["meta"]["concept_id"] == meta["concept_id"]

    def test_eventlog_accepts_concept_alias(self):
        log = EventLog()
        content, meta = create_concept_alias_payload(
            from_token="identity.PMM",
            to_token="identity.Echo",
            reason="Unified naming",
        )

        event_id = log.append(kind="concept_alias", content=content, meta=meta)
        assert event_id > 0

        event = log.get(event_id)
        assert event["kind"] == "concept_alias"

    def test_eventlog_accepts_concept_bind_event(self):
        log = EventLog()
        # Create a user message first
        msg_id = log.append(
            kind="user_message",
            content="Test message",
            meta={"source": "user"},
        )

        # Bind concept to that event
        content, meta = create_concept_bind_event_payload(
            event_id=msg_id,
            tokens=["topic.system_maturity"],
            relation="mention",
        )

        event_id = log.append(kind="concept_bind_event", content=content, meta=meta)
        assert event_id > 0

        event = log.get(event_id)
        assert event["kind"] == "concept_bind_event"

    def test_eventlog_accepts_concept_relate(self):
        log = EventLog()
        content, meta = create_concept_relate_payload(
            from_token="topic.system_maturity",
            to_token="policy.stability_v2",
            relation="influences",
        )

        event_id = log.append(kind="concept_relate", content=content, meta=meta)
        assert event_id > 0

        event = log.get(event_id)
        assert event["kind"] == "concept_relate"

    def test_eventlog_accepts_concept_state_snapshot(self):
        log = EventLog()
        content, meta = create_concept_state_snapshot_payload(
            up_to_event_id=100,
            concept_counts={"identity.Echo": 5},
            binding_counts={"identity.Echo": 10},
            edge_counts={"influences": 3},
        )

        event_id = log.append(kind="concept_state_snapshot", content=content, meta=meta)
        assert event_id > 0

        event = log.get(event_id)
        assert event["kind"] == "concept_state_snapshot"

    def test_eventlog_hash_chain_for_concept_events(self):
        log = EventLog()
        content, meta = create_concept_define_payload(
            token="policy.test",
            concept_kind="policy",
            definition="Test policy",
        )

        # Append concept event
        id1 = log.append(kind="concept_define", content=content, meta=meta)
        event1 = log.get(id1)

        # Hash chain should be maintained
        assert event1["hash"] is not None
        assert event1["prev_hash"] is None  # First event

        # Append another concept event
        content2, meta2 = create_concept_alias_payload(
            from_token="test.a", to_token="test.b"
        )
        id2 = log.append(kind="concept_alias", content=content2, meta=meta2)
        event2 = log.get(id2)

        # Second event should chain to first
        assert event2["prev_hash"] == event1["hash"]

    def test_all_ctl_kinds_in_valid_kinds(self):
        log = EventLog()

        # All CTL kinds should be accepted
        ctl_kinds = [
            "concept_define",
            "concept_alias",
            "concept_bind_event",
            "concept_relate",
            "concept_state_snapshot",
        ]

        for kind in ctl_kinds:
            # Create minimal valid payload
            if kind == "concept_define":
                content, meta = create_concept_define_payload(
                    token=f"test.{kind}",
                    concept_kind="test",
                    definition="Test",
                )
            elif kind == "concept_alias":
                content, meta = create_concept_alias_payload(
                    from_token="a", to_token="b"
                )
            elif kind == "concept_bind_event":
                content, meta = create_concept_bind_event_payload(
                    event_id=1, tokens=["test"]
                )
            elif kind == "concept_relate":
                content, meta = create_concept_relate_payload(
                    from_token="a", to_token="b", relation="test"
                )
            elif kind == "concept_state_snapshot":
                content, meta = create_concept_state_snapshot_payload(
                    up_to_event_id=1,
                    concept_counts={},
                    binding_counts={},
                    edge_counts={},
                )

            # Should not raise ValueError
            event_id = log.append(kind=kind, content=content, meta=meta)
            assert event_id > 0
