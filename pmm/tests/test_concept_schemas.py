# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_concept_schemas.py
"""Tests for Concept Token Layer schema validation."""

import json
import pytest

from pmm.core.concept_schemas import (
    create_concept_define_payload,
    create_concept_alias_payload,
    create_concept_bind_event_payload,
    create_concept_relate_payload,
    create_concept_state_snapshot_payload,
    validate_concept_define,
    validate_concept_alias,
    validate_concept_bind_event,
    validate_concept_relate,
    validate_concept_state_snapshot,
    validate_concept_event,
)


class TestConceptDefine:
    def test_create_valid_concept_define(self):
        content, meta = create_concept_define_payload(
            token="identity.Echo",
            concept_kind="identity",
            definition="Primary identity facet for PMM",
            attributes={"priority": 0.9, "scope": "system"},
            version=1,
            source="user",
        )

        # Validate structure
        data = json.loads(content)
        assert data["token"] == "identity.Echo"
        assert data["concept_kind"] == "identity"
        assert data["definition"] == "Primary identity facet for PMM"
        assert data["attributes"]["priority"] == 0.9
        assert data["version"] == 1

        assert "concept_id" in meta
        assert meta["source"] == "user"
        assert len(meta["concept_id"]) == 64  # sha256 hex

        # Should validate without error
        validate_concept_define(content, meta)

    def test_concept_define_deterministic_id(self):
        # Same payload should produce same concept_id
        content1, meta1 = create_concept_define_payload(
            token="policy.stability_v2",
            concept_kind="policy",
            definition="Stability policy version 2",
        )
        content2, meta2 = create_concept_define_payload(
            token="policy.stability_v2",
            concept_kind="policy",
            definition="Stability policy version 2",
        )

        assert content1 == content2
        assert meta1["concept_id"] == meta2["concept_id"]

    def test_concept_define_different_content_different_id(self):
        content1, meta1 = create_concept_define_payload(
            token="topic.system_maturity",
            concept_kind="topic",
            definition="System maturity level",
        )
        content2, meta2 = create_concept_define_payload(
            token="topic.system_maturity",
            concept_kind="topic",
            definition="System maturity level v2",  # Different definition
        )

        assert content1 != content2
        assert meta1["concept_id"] != meta2["concept_id"]

    def test_concept_define_with_supersedes(self):
        old_content, old_meta = create_concept_define_payload(
            token="policy.stability_v1",
            concept_kind="policy",
            definition="Old stability policy",
        )

        new_content, new_meta = create_concept_define_payload(
            token="policy.stability_v2",
            concept_kind="policy",
            definition="New stability policy",
            supersedes=old_meta["concept_id"],
        )

        assert new_meta["supersedes"] == old_meta["concept_id"]
        validate_concept_define(new_content, new_meta)

    def test_concept_define_validation_errors(self):
        # Missing token
        with pytest.raises(ValueError, match="token"):
            create_concept_define_payload(
                token="",
                concept_kind="policy",
                definition="Test",
            )

        # Missing concept_kind
        with pytest.raises(ValueError, match="concept_kind"):
            create_concept_define_payload(
                token="test.token",
                concept_kind="",
                definition="Test",
            )

        # Missing definition
        with pytest.raises(ValueError, match="definition"):
            create_concept_define_payload(
                token="test.token",
                concept_kind="policy",
                definition="",
            )

        # Invalid version
        with pytest.raises(ValueError, match="version"):
            create_concept_define_payload(
                token="test.token",
                concept_kind="policy",
                definition="Test",
                version=0,
            )

    def test_concept_define_id_mismatch_detection(self):
        content, meta = create_concept_define_payload(
            token="test.token",
            concept_kind="policy",
            definition="Test",
        )

        # Tamper with concept_id
        meta["concept_id"] = "wrong_id"

        with pytest.raises(ValueError, match="concept_id mismatch"):
            validate_concept_define(content, meta)


class TestConceptAlias:
    def test_create_valid_concept_alias(self):
        content, meta = create_concept_alias_payload(
            from_token="topic.system_resilience",
            to_token="topic.system_maturity",
            reason="Unified terminology",
            source="user",
        )

        data = json.loads(content)
        assert data["from"] == "topic.system_resilience"
        assert data["to"] == "topic.system_maturity"
        assert data["reason"] == "Unified terminology"

        assert "alias_id" in meta
        assert meta["source"] == "user"

        validate_concept_alias(content, meta)

    def test_concept_alias_deterministic_id(self):
        content1, meta1 = create_concept_alias_payload(
            from_token="identity.PMM",
            to_token="identity.Echo",
        )
        content2, meta2 = create_concept_alias_payload(
            from_token="identity.PMM",
            to_token="identity.Echo",
        )

        assert content1 == content2
        assert meta1["alias_id"] == meta2["alias_id"]

    def test_concept_alias_validation_errors(self):
        with pytest.raises(ValueError, match="from_token"):
            create_concept_alias_payload(
                from_token="",
                to_token="identity.Echo",
            )

        with pytest.raises(ValueError, match="to_token"):
            create_concept_alias_payload(
                from_token="identity.PMM",
                to_token="",
            )


class TestConceptBindEvent:
    def test_create_valid_concept_bind_event(self):
        content, meta = create_concept_bind_event_payload(
            event_id=42,
            tokens=["topic.system_maturity", "policy.stability_v2"],
            relation="evidence",
            weight=0.8,
            source="reflection",
        )

        data = json.loads(content)
        assert data["event_id"] == 42
        assert data["tokens"] == ["topic.system_maturity", "policy.stability_v2"]
        assert data["relation"] == "evidence"
        assert data["weight"] == 0.8

        assert "binding_id" in meta
        assert meta["source"] == "reflection"

        validate_concept_bind_event(content, meta)

    def test_concept_bind_event_deterministic_id(self):
        content1, meta1 = create_concept_bind_event_payload(
            event_id=100,
            tokens=["identity.Echo"],
            relation="mention",
        )
        content2, meta2 = create_concept_bind_event_payload(
            event_id=100,
            tokens=["identity.Echo"],
            relation="mention",
        )

        assert content1 == content2
        assert meta1["binding_id"] == meta2["binding_id"]

    def test_concept_bind_event_different_event_different_id(self):
        content1, meta1 = create_concept_bind_event_payload(
            event_id=100,
            tokens=["identity.Echo"],
        )
        content2, meta2 = create_concept_bind_event_payload(
            event_id=101,
            tokens=["identity.Echo"],
        )

        assert content1 != content2
        assert meta1["binding_id"] != meta2["binding_id"]

    def test_concept_bind_event_validation_errors(self):
        with pytest.raises(ValueError, match="event_id"):
            create_concept_bind_event_payload(
                event_id=0,
                tokens=["identity.Echo"],
            )

        with pytest.raises(ValueError, match="tokens"):
            create_concept_bind_event_payload(
                event_id=42,
                tokens=[],
            )

        with pytest.raises(ValueError, match="tokens"):
            create_concept_bind_event_payload(
                event_id=42,
                tokens=["valid", ""],  # Empty string in list
            )

        with pytest.raises(ValueError, match="relation"):
            create_concept_bind_event_payload(
                event_id=42,
                tokens=["identity.Echo"],
                relation="",
            )


class TestConceptRelate:
    def test_create_valid_concept_relate(self):
        content, meta = create_concept_relate_payload(
            from_token="topic.system_maturity",
            to_token="policy.stability_v2",
            relation="influences",
            weight=0.9,
            source="autonomy_kernel",
        )

        data = json.loads(content)
        assert data["from"] == "topic.system_maturity"
        assert data["to"] == "policy.stability_v2"
        assert data["relation"] == "influences"
        assert data["weight"] == 0.9

        assert "relation_id" in meta
        assert meta["source"] == "autonomy_kernel"

        validate_concept_relate(content, meta)

    def test_concept_relate_deterministic_id(self):
        content1, meta1 = create_concept_relate_payload(
            from_token="ontology.Self(x)",
            to_token="ontology.Identity(x)",
            relation="depends_on",
        )
        content2, meta2 = create_concept_relate_payload(
            from_token="ontology.Self(x)",
            to_token="ontology.Identity(x)",
            relation="depends_on",
        )

        assert content1 == content2
        assert meta1["relation_id"] == meta2["relation_id"]

    def test_concept_relate_validation_errors(self):
        with pytest.raises(ValueError, match="from_token"):
            create_concept_relate_payload(
                from_token="",
                to_token="policy.stability_v2",
                relation="influences",
            )

        with pytest.raises(ValueError, match="to_token"):
            create_concept_relate_payload(
                from_token="topic.system_maturity",
                to_token="",
                relation="influences",
            )

        with pytest.raises(ValueError, match="relation"):
            create_concept_relate_payload(
                from_token="topic.system_maturity",
                to_token="policy.stability_v2",
                relation="",
            )


class TestConceptStateSnapshot:
    def test_create_valid_concept_state_snapshot(self):
        content, meta = create_concept_state_snapshot_payload(
            up_to_event_id=1000,
            concept_counts={"identity.Echo": 5, "policy.stability_v2": 3},
            binding_counts={"identity.Echo": 12, "policy.stability_v2": 8},
            edge_counts={"influences": 4, "depends_on": 2},
            source="autonomy_kernel",
        )

        data = json.loads(content)
        assert data["up_to_event_id"] == 1000
        assert data["concept_counts"]["identity.Echo"] == 5
        assert data["binding_counts"]["identity.Echo"] == 12
        assert data["edge_counts"]["influences"] == 4

        assert "snapshot_id" in meta
        assert meta["source"] == "autonomy_kernel"

        validate_concept_state_snapshot(content, meta)

    def test_concept_state_snapshot_deterministic_id(self):
        content1, meta1 = create_concept_state_snapshot_payload(
            up_to_event_id=500,
            concept_counts={"identity.Echo": 1},
            binding_counts={"identity.Echo": 2},
            edge_counts={},
        )
        content2, meta2 = create_concept_state_snapshot_payload(
            up_to_event_id=500,
            concept_counts={"identity.Echo": 1},
            binding_counts={"identity.Echo": 2},
            edge_counts={},
        )

        assert content1 == content2
        assert meta1["snapshot_id"] == meta2["snapshot_id"]

    def test_concept_state_snapshot_validation_errors(self):
        with pytest.raises(ValueError, match="up_to_event_id"):
            create_concept_state_snapshot_payload(
                up_to_event_id=-1,
                concept_counts={},
                binding_counts={},
                edge_counts={},
            )


class TestUnifiedValidation:
    def test_validate_concept_event_dispatcher(self):
        # Test that the unified validator dispatches correctly
        content, meta = create_concept_define_payload(
            token="test.token",
            concept_kind="test",
            definition="Test definition",
        )

        # Should not raise
        validate_concept_event("concept_define", content, meta)

        # Unknown kind
        with pytest.raises(ValueError, match="Unknown concept event kind"):
            validate_concept_event("unknown_kind", content, meta)

    def test_all_concept_kinds_have_validators(self):
        # Ensure all CTL event kinds have validators
        kinds = [
            "concept_define",
            "concept_alias",
            "concept_bind_event",
            "concept_relate",
            "concept_state_snapshot",
        ]

        for kind in kinds:
            # Create valid payload for each kind
            if kind == "concept_define":
                content, meta = create_concept_define_payload(
                    token="test", concept_kind="test", definition="test"
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

            # Should not raise
            validate_concept_event(kind, content, meta)
