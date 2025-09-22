"""Tests for DirectiveHierarchy class.

Comprehensive test suite covering deterministic tree building, priority assignment,
idempotent event emission, and CONTRIBUTING.md compliance.
"""

from pmm.runtime.hierarchy.directive_hierarchy import DirectiveHierarchy


class MockEventLog:
    """Mock event log for testing."""

    def __init__(self):
        self.events = []
        self.next_id = 1

    def append(self, kind: str, content: str, meta: dict) -> str:
        event_id = f"event_{self.next_id}"
        self.next_id += 1
        event = {"id": event_id, "kind": kind, "content": content, "meta": meta}
        self.events.append(event)
        return event_id

    def read_all(self):
        return self.events


def test_build_tree_empty():
    """Test tree building with empty/invalid event lists."""
    hierarchy = DirectiveHierarchy()

    # Empty list
    result = hierarchy.build_tree([])
    assert result["nodes"] == {}
    assert result["relationships"]["parent_child"] == {}
    assert result["metadata"]["total_events"] == 0
    assert result["metadata"]["directive_events"] == 0
    assert result["metadata"]["tree_depth"] == 0

    # None input
    result = hierarchy.build_tree(None)
    assert result["nodes"] == {}

    # List with non-dict items
    result = hierarchy.build_tree(["invalid", None, 123])
    assert result["metadata"]["total_events"] == 3
    assert result["metadata"]["directive_events"] == 0


def test_build_tree_basic():
    """Test basic tree building with directive events."""
    hierarchy = DirectiveHierarchy()

    events = [
        {
            "id": "event_1",
            "kind": "commitment_open",
            "content": "I will complete the project",
            "meta": {"timestamp": 1000},
        },
        {
            "id": "event_2",
            "kind": "reflection",
            "content": "Reflecting on my progress",
            "meta": {"timestamp": 1100},
        },
        {
            "id": "event_3",
            "kind": "policy_update",
            "content": "Updated work policy",
            "meta": {"timestamp": 900},
        },
    ]

    result = hierarchy.build_tree(events)

    assert result["metadata"]["total_events"] == 3
    assert result["metadata"]["directive_events"] == 3
    assert len(result["nodes"]) == 3

    # Check node creation
    assert "event_1" in result["nodes"]
    assert "event_2" in result["nodes"]
    assert "event_3" in result["nodes"]

    # Check node properties
    commitment_node = result["nodes"]["event_1"]
    assert commitment_node["type"] == "commitment_open"
    assert commitment_node["commitment_state"] == "open"


def test_build_tree_commitment_states():
    """Test commitment open/close state tracking."""
    hierarchy = DirectiveHierarchy()

    events = [
        {
            "id": "event_1",
            "kind": "commitment_open",
            "content": "I will exercise daily",
            "meta": {"timestamp": 1000},
        },
        {
            "id": "event_2",
            "kind": "commitment_close",
            "content": "Completed exercise commitment",
            "meta": {"timestamp": 2000, "commitment_id": "event_1"},
        },
    ]

    result = hierarchy.build_tree(events)

    # Check commitment state tracking
    open_node = result["nodes"]["event_1"]
    close_node = result["nodes"]["event_2"]

    assert open_node["commitment_state"] == "closed"  # Updated by close event
    assert close_node["parent"] == "event_1"
    assert "event_2" in open_node["children"]


def test_build_tree_relationships():
    """Test parent-child relationship building."""
    hierarchy = DirectiveHierarchy()

    events = [
        {
            "id": "policy_1",
            "kind": "policy_update",
            "content": "Focus on health and fitness goals",
            "meta": {"timestamp": 1000},
        },
        {
            "id": "commit_1",
            "kind": "commitment_open",
            "content": "I will exercise and stay healthy",
            "meta": {"timestamp": 1100},
        },
        {
            "id": "reflect_1",
            "kind": "reflection",
            "content": "Reflecting on my exercise routine",
            "meta": {"timestamp": 1200},
        },
    ]

    result = hierarchy.build_tree(events)

    # Check hierarchical relationships
    nodes = result["nodes"]

    # Reflection should be child of commitment (temporal proximity)
    assert nodes["reflect_1"]["parent"] == "commit_1"
    assert "reflect_1" in nodes["commit_1"]["children"]

    # Commitment should be child of policy (thematic similarity)
    assert nodes["commit_1"]["parent"] == "policy_1"
    assert "commit_1" in nodes["policy_1"]["children"]


def test_assign_priorities_empty():
    """Test priority assignment with empty tree."""
    hierarchy = DirectiveHierarchy()

    empty_tree = {"nodes": {}, "relationships": {}}
    result = hierarchy.assign_priorities(empty_tree)

    assert result == empty_tree


def test_assign_priorities_basic():
    """Test basic priority assignment."""
    hierarchy = DirectiveHierarchy()

    tree = {
        "nodes": {
            "commit_1": {
                "id": "commit_1",
                "type": "commitment_open",
                "commitment_state": "open",
                "children": ["reflect_1"],
                "parent": None,
            },
            "reflect_1": {
                "id": "reflect_1",
                "type": "reflection",
                "children": [],
                "parent": "commit_1",
            },
            "policy_1": {
                "id": "policy_1",
                "type": "policy_update",
                "children": [],
                "parent": None,
            },
        },
        "relationships": {},
        "metadata": {},
    }

    result = hierarchy.assign_priorities(tree)

    # Check priority assignments
    nodes = result["nodes"]
    assert nodes["commit_1"]["priority"] == 1.0  # 1.0 base (clamped at 1.0)
    assert nodes["reflect_1"]["priority"] == 0.6  # reflection base priority
    assert nodes["policy_1"]["priority"] == 0.4  # policy base priority

    # Check priority ordering
    priority_order = result["priority_order"]
    assert priority_order[0] == "commit_1"  # Highest priority first


def test_assign_priorities_clamping():
    """Test priority clamping to [0.0, 1.0] range."""
    hierarchy = DirectiveHierarchy()

    tree = {
        "nodes": {
            "commit_1": {
                "id": "commit_1",
                "type": "commitment_open",
                "commitment_state": "open",
                "children": [
                    "child_1",
                    "child_2",
                    "child_3",
                    "child_4",
                    "child_5",
                    "child_6",
                ],
                "parent": None,
            }
        },
        "relationships": {},
        "metadata": {},
    }

    result = hierarchy.assign_priorities(tree)

    # Priority should be clamped to 1.0 (1.0 base + 0.5 max boost = 1.5 -> 1.0)
    assert result["nodes"]["commit_1"]["priority"] == 1.0


def test_assign_priorities_commitment_states():
    """Test priority assignment for different commitment states."""
    hierarchy = DirectiveHierarchy()

    tree = {
        "nodes": {
            "open_commit": {
                "id": "open_commit",
                "type": "commitment_open",
                "commitment_state": "open",
                "children": [],
                "parent": None,
            },
            "closed_commit": {
                "id": "closed_commit",
                "type": "commitment_open",
                "commitment_state": "closed",
                "children": [],
                "parent": None,
            },
        },
        "relationships": {},
        "metadata": {},
    }

    result = hierarchy.assign_priorities(tree)

    # Open commitments should have higher priority than closed
    nodes = result["nodes"]
    assert nodes["open_commit"]["priority"] == 1.0  # commitment_open
    assert nodes["closed_commit"]["priority"] == 0.8  # commitment_close


def test_maybe_emit_update_new():
    """Test emitting new hierarchy update event."""
    hierarchy = DirectiveHierarchy()
    eventlog = MockEventLog()

    tree = {
        "nodes": {
            "node_1": {"id": "node_1", "type": "commitment_open", "priority": 1.0}
        },
        "relationships": {"parent_child": {}},
        "metadata": {"node_count": 1, "tree_depth": 1},
    }

    event_id = hierarchy.maybe_emit_update(eventlog, "src_123", tree)

    assert event_id is not None
    assert len(eventlog.events) == 1

    event = eventlog.events[0]
    assert event["kind"] == "directive_hierarchy_update"
    assert event["content"] == "hierarchy"
    assert event["meta"]["component"] == "directive_hierarchy"
    assert event["meta"]["src_event_id"] == "src_123"
    assert event["meta"]["deterministic"] is True
    assert "digest" in event["meta"]


def test_maybe_emit_update_idempotent():
    """Test idempotent event emission (duplicate prevention)."""
    hierarchy = DirectiveHierarchy()
    eventlog = MockEventLog()

    tree = {
        "nodes": {"node_1": {"id": "node_1", "type": "reflection", "priority": 0.6}},
        "relationships": {"parent_child": {}},
        "metadata": {"node_count": 1, "tree_depth": 1},
    }

    # First emission
    event_id1 = hierarchy.maybe_emit_update(eventlog, "src_123", tree)
    assert event_id1 is not None
    assert len(eventlog.events) == 1

    # Second emission with same data - should be skipped
    event_id2 = hierarchy.maybe_emit_update(eventlog, "src_123", tree)
    assert event_id2 is None
    assert len(eventlog.events) == 1  # No new event


def test_maybe_emit_update_different_data():
    """Test that different tree data produces new events."""
    hierarchy = DirectiveHierarchy()
    eventlog = MockEventLog()

    tree1 = {
        "nodes": {
            "node_1": {"id": "node_1", "type": "commitment_open", "priority": 1.0}
        },
        "relationships": {"parent_child": {}},
        "metadata": {"node_count": 1, "tree_depth": 1},
    }
    tree2 = {
        "nodes": {"node_2": {"id": "node_2", "type": "reflection", "priority": 0.6}},
        "relationships": {"parent_child": {}},
        "metadata": {"node_count": 1, "tree_depth": 1},
    }

    # First emission
    event_id1 = hierarchy.maybe_emit_update(eventlog, "src_123", tree1)
    assert event_id1 is not None

    # Second emission with different data - should create new event
    event_id2 = hierarchy.maybe_emit_update(eventlog, "src_124", tree2)
    assert event_id2 is not None
    assert len(eventlog.events) == 2


def test_deterministic_behavior():
    """Test that tree building is deterministic across multiple runs."""
    hierarchy = DirectiveHierarchy()

    events = [
        {
            "id": "event_1",
            "kind": "commitment_open",
            "content": "I will learn new skills",
            "meta": {"timestamp": 1000},
        },
        {
            "id": "event_2",
            "kind": "reflection",
            "content": "Reflecting on learning progress",
            "meta": {"timestamp": 1100},
        },
    ]

    # Run tree building multiple times
    results = []
    for _ in range(3):
        tree = hierarchy.build_tree(events)
        tree = hierarchy.assign_priorities(tree)
        results.append(tree)

    # All results should be identical
    for i in range(1, len(results)):
        assert results[i] == results[0]


def test_deterministic_digest():
    """Test that digest generation is deterministic."""
    hierarchy = DirectiveHierarchy()

    tree = {
        "nodes": {
            "node_1": {
                "id": "node_1",
                "type": "commitment_open",
                "priority": 1.0,
                "children": [],
                "parent": None,
            }
        },
        "relationships": {"parent_child": {}},
        "metadata": {"node_count": 1, "tree_depth": 1},
    }
    anomalies = ["orphaned_directives:1"]

    # Generate digest multiple times
    digests = []
    for _ in range(3):
        digest_data = hierarchy._serialize_for_digest(tree, anomalies)
        digests.append(digest_data)

    # All digests should be identical
    for digest in digests[1:]:
        assert digest == digests[0]


def test_anomaly_detection_orphaned():
    """Test detection of orphaned directives."""
    hierarchy = DirectiveHierarchy()

    tree = {
        "nodes": {
            "orphan_1": {
                "id": "orphan_1",
                "type": "reflection",
                "children": [],
                "parent": None,
            },
            "orphan_2": {
                "id": "orphan_2",
                "type": "policy_update",
                "children": [],
                "parent": None,
            },
        },
        "relationships": {"parent_child": {}},
        "metadata": {},
    }

    anomalies = hierarchy._detect_anomalies(tree)

    orphaned_flags = [a for a in anomalies if "orphaned_directives" in a]
    assert len(orphaned_flags) == 1
    assert "orphaned_directives:2" in orphaned_flags


def test_anomaly_detection_priority_inversions():
    """Test detection of priority inversions."""
    hierarchy = DirectiveHierarchy()

    tree = {
        "nodes": {
            "parent": {
                "id": "parent",
                "type": "policy_update",
                "priority": 0.4,
                "children": ["child"],
                "parent": None,
            },
            "child": {
                "id": "child",
                "type": "commitment_open",
                "priority": 1.0,
                "children": [],
                "parent": "parent",
            },
        },
        "relationships": {"parent_child": {"child": "parent"}},
        "metadata": {},
    }

    anomalies = hierarchy._detect_anomalies(tree)

    inversion_flags = [a for a in anomalies if "priority_inversions" in a]
    assert len(inversion_flags) == 1
    assert "priority_inversions:1" in inversion_flags


def test_anomaly_detection_excessive_depth():
    """Test detection of excessive tree depth."""
    hierarchy = DirectiveHierarchy(anomaly_threshold=2)

    tree = {
        "nodes": {},
        "relationships": {"parent_child": {}},
        "metadata": {"tree_depth": 5},
    }

    anomalies = hierarchy._detect_anomalies(tree)

    depth_flags = [a for a in anomalies if "excessive_depth" in a]
    assert len(depth_flags) == 1
    assert "excessive_depth:5" in depth_flags


def test_cycle_detection():
    """Test detection of cyclic dependencies."""
    hierarchy = DirectiveHierarchy()

    # Create nodes with circular references
    nodes = {
        "node_a": {"id": "node_a", "children": ["node_b"], "parent": "node_c"},
        "node_b": {"id": "node_b", "children": ["node_c"], "parent": "node_a"},
        "node_c": {"id": "node_c", "children": ["node_a"], "parent": "node_b"},
    }

    cycles = hierarchy._detect_cycles(nodes)
    assert len(cycles) > 0  # Should detect at least one cycle


def test_content_similarity():
    """Test content similarity calculation."""
    hierarchy = DirectiveHierarchy()

    # Identical content
    similarity = hierarchy._calculate_content_similarity("hello world", "hello world")
    assert similarity == 1.0

    # Partial overlap
    similarity = hierarchy._calculate_content_similarity(
        "hello world", "hello universe"
    )
    assert 0.0 < similarity < 1.0

    # No overlap
    similarity = hierarchy._calculate_content_similarity("hello world", "foo bar")
    assert similarity == 0.0

    # Empty content
    similarity = hierarchy._calculate_content_similarity("", "hello world")
    assert similarity == 0.0


def test_tree_depth_calculation():
    """Test tree depth calculation."""
    hierarchy = DirectiveHierarchy()

    # Single level tree
    nodes = {
        "root": {"id": "root", "children": ["child1", "child2"], "parent": None},
        "child1": {"id": "child1", "children": [], "parent": "root"},
        "child2": {"id": "child2", "children": [], "parent": "root"},
    }

    depth = hierarchy._calculate_tree_depth(nodes, {})
    assert depth == 2  # Root + 1 level of children

    # Multi-level tree
    nodes = {
        "root": {"id": "root", "children": ["child1"], "parent": None},
        "child1": {"id": "child1", "children": ["grandchild1"], "parent": "root"},
        "grandchild1": {"id": "grandchild1", "children": [], "parent": "child1"},
    }

    depth = hierarchy._calculate_tree_depth(nodes, {})
    assert depth == 3  # Root + child + grandchild


def test_integration_workflow():
    """Test complete integration workflow: build -> assign -> emit."""
    hierarchy = DirectiveHierarchy()
    eventlog = MockEventLog()

    # Simulate event sequence with hierarchy
    events = [
        {
            "id": "policy_1",
            "kind": "policy_update",
            "content": "Focus on productivity and learning",
            "meta": {"timestamp": 1000},
        },
        {
            "id": "commit_1",
            "kind": "commitment_open",
            "content": "I will learn programming and be productive",
            "meta": {"timestamp": 1100},
        },
        {
            "id": "reflect_1",
            "kind": "reflection",
            "content": "Reflecting on my learning progress and productivity",
            "meta": {"timestamp": 1200},
        },
    ]

    # Step 1: Build tree
    tree = hierarchy.build_tree(events)
    assert len(tree["nodes"]) == 3

    # Step 2: Assign priorities
    tree = hierarchy.assign_priorities(tree)
    assert all("priority" in node for node in tree["nodes"].values())

    # Step 3: Emit update
    event_id = hierarchy.maybe_emit_update(eventlog, "src_hierarchy_456", tree)
    assert event_id is not None

    # Verify event structure
    event = eventlog.events[0]
    assert event["kind"] == "directive_hierarchy_update"
    assert event["meta"]["tree"] == tree
    assert event["meta"]["src_event_id"] == "src_hierarchy_456"


def test_metadata_preservation():
    """Test that all metadata is properly preserved in events."""
    hierarchy = DirectiveHierarchy(anomaly_threshold=10)
    eventlog = MockEventLog()

    tree = {
        "nodes": {
            "node_1": {"id": "node_1", "type": "commitment_open", "priority": 1.0}
        },
        "relationships": {"parent_child": {}},
        "metadata": {"node_count": 1, "tree_depth": 1},
    }

    hierarchy.maybe_emit_update(eventlog, "src_789", tree)

    event = eventlog.events[0]
    meta = event["meta"]

    # Check all required metadata fields
    assert meta["component"] == "directive_hierarchy"
    assert meta["src_event_id"] == "src_789"
    assert meta["deterministic"] is True
    assert meta["node_count"] == 1
    assert meta["tree_depth"] == 1
    assert meta["priority_weights"] == hierarchy.PRIORITY_WEIGHTS
    assert meta["anomaly_threshold"] == 10
    assert "digest" in meta
    assert "anomalies" in meta


def test_edge_cases():
    """Test edge cases: malformed events, missing fields."""
    hierarchy = DirectiveHierarchy()

    # Events with missing fields
    events = [
        {"kind": "commitment_open"},  # Missing id, content
        {"id": "event_2", "content": "test"},  # Missing kind
        {"id": "event_3", "kind": "unknown_type", "content": "test"},  # Unknown type
    ]

    result = hierarchy.build_tree(events)

    # Should handle gracefully
    assert result["metadata"]["total_events"] == 3
    # Only commitment_open should be processed (despite missing fields)
    assert result["metadata"]["directive_events"] == 1


def test_replayability():
    """Test that ledger replay yields identical hierarchy updates."""
    hierarchy = DirectiveHierarchy()

    # Same input events
    events = [
        {
            "id": "event_1",
            "kind": "commitment_open",
            "content": "I will exercise daily",
            "meta": {"timestamp": 1000},
        }
    ]

    # Generate multiple hierarchy updates with same data
    eventlogs = [MockEventLog() for _ in range(3)]
    event_ids = []

    for eventlog in eventlogs:
        tree = hierarchy.build_tree(events)
        tree = hierarchy.assign_priorities(tree)
        event_id = hierarchy.maybe_emit_update(eventlog, "src_replay_test", tree)
        event_ids.append(event_id)

    # All should produce events (first time)
    assert all(eid is not None for eid in event_ids)

    # All events should have identical metadata (except event IDs)
    events_emitted = [eventlog.events[0] for eventlog in eventlogs]
    for i in range(1, len(events_emitted)):
        assert (
            events_emitted[i]["meta"]["digest"] == events_emitted[0]["meta"]["digest"]
        )
        assert events_emitted[i]["meta"]["tree"] == events_emitted[0]["meta"]["tree"]
        assert (
            events_emitted[i]["meta"]["anomalies"]
            == events_emitted[0]["meta"]["anomalies"]
        )


def test_custom_anomaly_threshold():
    """Test custom anomaly threshold configuration."""
    hierarchy = DirectiveHierarchy(anomaly_threshold=3)

    tree = {
        "nodes": {},
        "relationships": {"parent_child": {}},
        "metadata": {"tree_depth": 4},
    }

    anomalies = hierarchy._detect_anomalies(tree)

    # Should detect excessive depth with threshold 3
    depth_flags = [a for a in anomalies if "excessive_depth" in a]
    assert len(depth_flags) == 1
    assert "excessive_depth:4" in depth_flags
