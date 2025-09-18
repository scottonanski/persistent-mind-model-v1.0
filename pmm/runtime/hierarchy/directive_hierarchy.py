"""Directive Hierarchy System for PMM.

Deterministic, event-driven system that organizes commitments, policies, and reflections
into a hierarchical directive tree, ensuring traceable priority and dependency relationships
with full ledger integrity.
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional, Set
import hashlib
import re


class DirectiveHierarchy:
    """
    Deterministic directive hierarchy system that reconstructs directive trees from events
    and assigns priorities with full auditability through the event ledger.
    """

    # Deterministic priority weights for directive types
    PRIORITY_WEIGHTS = {
        "commitment_open": 1.0,  # Highest priority - active commitments
        "commitment_closed": 0.8,  # High priority - completed commitments
        "reflection": 0.6,  # Medium priority - reflections
        "policy_update": 0.4,  # Lower priority - policy changes
        "stage_update": 0.2,  # Lowest priority - stage transitions
    }

    # Event types that create directive nodes
    DIRECTIVE_EVENT_TYPES = {
        "commitment_open",
        "commitment_close",
        "reflection",
        "policy_update",
        "stage_update",
        "trait_update",
    }

    def __init__(self, anomaly_threshold: int = 5):
        """Initialize directive hierarchy analyzer.

        Args:
            anomaly_threshold: Maximum depth for anomaly detection
        """
        self.anomaly_threshold = anomaly_threshold

    def build_tree(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Pure function.
        Reconstruct directive tree from commitments, policies, reflections.

        Args:
            events: List of event dictionaries from event log

        Returns:
            Tree dict with directive nodes, relationships, and metadata
        """
        if not events or not isinstance(events, list):
            return {
                "nodes": {},
                "relationships": {"parent_child": {}, "dependencies": {}},
                "metadata": {
                    "total_events": 0,
                    "directive_events": 0,
                    "tree_depth": 0,
                    "node_count": 0,
                },
            }

        # Filter and process directive events
        directive_events = []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_kind = event.get("kind", "")
            if event_kind in self.DIRECTIVE_EVENT_TYPES:
                directive_events.append(event)

        # Build directive nodes
        nodes = {}
        commitment_states = {}  # Track open/closed commitments

        for event in directive_events:
            event_id = event.get("id", "")
            event_kind = event.get("kind", "")
            content = event.get("content", "")
            meta = event.get("meta", {})

            # Create node for this directive
            node = {
                "id": event_id,
                "type": event_kind,
                "content": content,
                "meta": meta,
                "priority": 0.0,  # Will be assigned later
                "children": [],
                "parent": None,
            }

            # Handle commitment state tracking
            if event_kind == "commitment_open":
                commitment_states[event_id] = "open"
                node["commitment_state"] = "open"
            elif event_kind == "commitment_close":
                # Find the corresponding open commitment
                commitment_id = meta.get("commitment_id", "")
                if commitment_id in commitment_states:
                    commitment_states[commitment_id] = "closed"
                    # Link close to open
                    if commitment_id in nodes:
                        nodes[commitment_id]["commitment_state"] = "closed"
                        node["parent"] = commitment_id
                        nodes[commitment_id]["children"].append(event_id)

            nodes[event_id] = node

        # Build parent-child relationships deterministically
        relationships = self._build_relationships(nodes, directive_events)

        # Calculate tree metadata
        tree_depth = self._calculate_tree_depth(nodes, relationships)

        return {
            "nodes": nodes,
            "relationships": relationships,
            "metadata": {
                "total_events": len(events),
                "directive_events": len(directive_events),
                "tree_depth": tree_depth,
                "node_count": len(nodes),
            },
        }

    def assign_priorities(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pure function.
        Deterministic scoring of directives with clamped priority weights.

        Args:
            tree: Tree dict from build_tree()

        Returns:
            Updated tree with priority assignments
        """
        if not tree or "nodes" not in tree:
            return tree

        nodes = tree["nodes"]

        # Assign base priorities from event types
        for node_id, node in nodes.items():
            event_kind = node.get("type", "")
            base_priority = self.PRIORITY_WEIGHTS.get(event_kind, 0.0)

            # Adjust priority based on commitment state
            if event_kind == "commitment_open":
                commitment_state = node.get("commitment_state", "open")
                if commitment_state == "open":
                    base_priority = self.PRIORITY_WEIGHTS["commitment_open"]
                else:
                    base_priority = self.PRIORITY_WEIGHTS["commitment_closed"]

            # Boost priority for nodes with children (parent directives)
            children_count = len(node.get("children", []))
            if children_count > 0:
                base_priority += 0.1 * min(children_count, 5)  # Cap boost at 0.5

            # Clamp priority to [0.0, 1.0] range
            node["priority"] = max(0.0, min(1.0, base_priority))

        # Sort nodes by priority for deterministic ordering
        priority_order = []
        for node_id, node in nodes.items():
            priority_order.append((node["priority"], node_id, node))

        # Sort by priority (descending), then by node_id (ascending) for determinism
        priority_order.sort(key=lambda x: (-x[0], x[1]))

        # Update tree with priority metadata
        tree["priority_order"] = [item[1] for item in priority_order]
        if "metadata" not in tree:
            tree["metadata"] = {}
        tree["metadata"]["highest_priority"] = (
            priority_order[0][0] if priority_order else 0.0
        )
        tree["metadata"]["lowest_priority"] = (
            priority_order[-1][0] if priority_order else 0.0
        )

        return tree

    def maybe_emit_update(
        self, eventlog, src_event_id: str, tree: Dict[str, Any]
    ) -> Optional[str]:
        """
        Emit directive_hierarchy_update event with digest deduplication.
        Event shape:
          kind="directive_hierarchy_update"
          content="hierarchy"
          meta={
            "component": "directive_hierarchy",
            "tree": tree,
            "digest": <SHA256 over serialized tree>,
            "src_event_id": src_event_id,
            "deterministic": True,
            "anomalies": detected_anomalies,
            "node_count": node_count,
            "tree_depth": tree_depth
          }
        Returns event id or None if skipped due to idempotency.
        """
        # Detect anomalies before emission
        anomalies = self._detect_anomalies(tree)

        # Generate deterministic digest
        digest_data = self._serialize_for_digest(tree, anomalies)
        digest = hashlib.sha256(digest_data.encode()).hexdigest()

        # Check for existing event with same digest (idempotency)
        all_events = eventlog.read_all()
        for event in all_events[-20:]:  # Check recent events for efficiency
            if (
                event.get("kind") == "directive_hierarchy_update"
                and event.get("meta", {}).get("digest") == digest
            ):
                return None  # Skip - already exists

        # Prepare event metadata
        metadata = tree.get("metadata", {})
        meta = {
            "component": "directive_hierarchy",
            "tree": tree,
            "digest": digest,
            "src_event_id": src_event_id,
            "deterministic": True,
            "anomalies": anomalies,
            "node_count": metadata.get("node_count", 0),
            "tree_depth": metadata.get("tree_depth", 0),
            "priority_weights": self.PRIORITY_WEIGHTS,
            "anomaly_threshold": self.anomaly_threshold,
        }

        # Emit the hierarchy update event
        event_id = eventlog.append(
            kind="directive_hierarchy_update", content="hierarchy", meta=meta
        )

        return event_id

    def _build_relationships(
        self, nodes: Dict[str, Any], events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build deterministic parent-child relationships between directive nodes."""
        relationships = {"parent_child": {}, "dependencies": {}}

        # Group events by type for relationship building
        commitments = []
        reflections = []
        policies = []

        for event in events:
            event_kind = event.get("kind", "")
            if event_kind in ["commitment_open", "commitment_close"]:
                commitments.append(event)
            elif event_kind == "reflection":
                reflections.append(event)
            elif event_kind in ["policy_update", "stage_update", "trait_update"]:
                policies.append(event)

        # Build hierarchical relationships:
        # 1. Reflections are children of commitments (temporal proximity)
        # 2. Commitments are children of policies (thematic grouping)
        # 3. Policies form the root level

        # Sort events by timestamp for temporal relationships
        sorted(events, key=lambda e: e.get("meta", {}).get("timestamp", 0))

        # Link reflections to nearest preceding commitments
        for reflection in reflections:
            reflection_id = reflection.get("id", "")
            reflection_ts = reflection.get("meta", {}).get("timestamp", 0)

            # Find the most recent commitment before this reflection
            best_commitment = None
            best_distance = float("inf")

            for commitment in commitments:
                commitment_ts = commitment.get("meta", {}).get("timestamp", 0)
                if commitment_ts <= reflection_ts:
                    distance = reflection_ts - commitment_ts
                    if distance < best_distance:
                        best_distance = distance
                        best_commitment = commitment

            if best_commitment:
                commitment_id = best_commitment.get("id", "")
                if commitment_id in nodes and reflection_id in nodes:
                    nodes[reflection_id]["parent"] = commitment_id
                    nodes[commitment_id]["children"].append(reflection_id)
                    relationships["parent_child"][reflection_id] = commitment_id

        # Link commitments to policies (thematic grouping by content similarity)
        for commitment in commitments:
            commitment_id = commitment.get("id", "")
            commitment_content = commitment.get("content", "").lower()

            # Find the most thematically similar policy
            best_policy = None
            best_similarity = 0.0

            for policy in policies:
                policy_content = policy.get("content", "").lower()
                similarity = self._calculate_content_similarity(
                    commitment_content, policy_content
                )
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_policy = policy

            # Only link if similarity is above threshold
            if (
                best_policy and best_similarity > 0.05
            ):  # Lower threshold for better linking
                policy_id = best_policy.get("id", "")
                if policy_id in nodes and commitment_id in nodes:
                    nodes[commitment_id]["parent"] = policy_id
                    nodes[policy_id]["children"].append(commitment_id)
                    relationships["parent_child"][commitment_id] = policy_id

        return relationships

    def _calculate_content_similarity(self, content1: str, content2: str) -> float:
        """Calculate simple word overlap similarity between two content strings."""
        if not content1 or not content2:
            return 0.0

        # Normalize and tokenize
        words1 = set(re.findall(r"\b\w+\b", content1.lower()))
        words2 = set(re.findall(r"\b\w+\b", content2.lower()))

        if not words1 or not words2:
            return 0.0

        # Calculate Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _calculate_tree_depth(
        self, nodes: Dict[str, Any], relationships: Dict[str, Any]
    ) -> int:
        """Calculate maximum depth of the directive tree."""
        if not nodes:
            return 0

        max_depth = 0

        # Find root nodes (nodes with no parent)
        root_nodes = []
        for node_id, node in nodes.items():
            if not node.get("parent"):
                root_nodes.append(node_id)

        # Calculate depth from each root
        for root_id in root_nodes:
            depth = self._calculate_node_depth(root_id, nodes, set())
            max_depth = max(max_depth, depth)

        return max_depth

    def _calculate_node_depth(
        self, node_id: str, nodes: Dict[str, Any], visited: Set[str]
    ) -> int:
        """Recursively calculate depth of a node, avoiding cycles."""
        if node_id in visited or node_id not in nodes:
            return 0

        visited.add(node_id)
        node = nodes[node_id]
        children = node.get("children", [])

        if not children:
            return 1

        max_child_depth = 0
        for child_id in children:
            child_depth = self._calculate_node_depth(child_id, nodes, visited.copy())
            max_child_depth = max(max_child_depth, child_depth)

        return 1 + max_child_depth

    def _detect_anomalies(self, tree: Dict[str, Any]) -> List[str]:
        """Detect anomalies in the directive tree structure."""
        anomalies = []

        if not tree or "nodes" not in tree:
            return anomalies

        nodes = tree["nodes"]

        # Detect orphaned directives (nodes with no parent or children)
        orphaned_count = 0
        for node_id, node in nodes.items():
            if not node.get("parent") and not node.get("children"):
                orphaned_count += 1

        if orphaned_count > 0:
            anomalies.append(f"orphaned_directives:{orphaned_count}")

        # Detect cyclic dependencies
        cycles = self._detect_cycles(nodes)
        if cycles:
            anomalies.append(f"cyclic_dependencies:{len(cycles)}")

        # Detect priority inversions (child has higher priority than parent)
        inversions = 0
        for node_id, node in nodes.items():
            parent_id = node.get("parent")
            if parent_id and parent_id in nodes:
                parent_priority = nodes[parent_id].get("priority", 0.0)
                node_priority = node.get("priority", 0.0)
                if node_priority > parent_priority:
                    inversions += 1

        if inversions > 0:
            anomalies.append(f"priority_inversions:{inversions}")

        # Detect excessive tree depth
        tree_depth = tree.get("metadata", {}).get("tree_depth", 0)
        if tree_depth > self.anomaly_threshold:
            anomalies.append(f"excessive_depth:{tree_depth}")

        return anomalies

    def _detect_cycles(self, nodes: Dict[str, Any]) -> List[List[str]]:
        """Detect cycles in the directive tree using DFS."""
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node_id: str, path: List[str]) -> None:
            if node_id in rec_stack:
                # Found a cycle
                cycle_start = path.index(node_id)
                cycle = path[cycle_start:] + [node_id]
                cycles.append(cycle)
                return

            if node_id in visited or node_id not in nodes:
                return

            visited.add(node_id)
            rec_stack.add(node_id)

            node = nodes[node_id]
            children = node.get("children", [])

            for child_id in children:
                dfs(child_id, path + [node_id])

            rec_stack.remove(node_id)

        # Check all nodes as potential cycle starts
        for node_id in nodes:
            if node_id not in visited:
                dfs(node_id, [])

        return cycles

    def _serialize_for_digest(self, tree: Dict[str, Any], anomalies: List[str]) -> str:
        """Serialize tree and anomalies deterministically for digest generation."""
        parts = []

        # Add tree metadata
        metadata = tree.get("metadata", {})
        parts.append(f"total_events:{metadata.get('total_events', 0)}")
        parts.append(f"directive_events:{metadata.get('directive_events', 0)}")
        parts.append(f"tree_depth:{metadata.get('tree_depth', 0)}")
        parts.append(f"node_count:{metadata.get('node_count', 0)}")

        # Add nodes in sorted order
        nodes = tree.get("nodes", {})
        for node_id in sorted(nodes.keys()):
            node = nodes[node_id]
            parts.append(
                f"node:{node_id}:{node.get('type', '')}:{node.get('priority', 0.0):.6f}"
            )

            # Add parent relationship
            parent = node.get("parent")
            if parent:
                parts.append(f"parent:{node_id}:{parent}")

            # Add children relationships in sorted order
            children = sorted(node.get("children", []))
            for child in children:
                parts.append(f"child:{node_id}:{child}")

        # Add priority order
        priority_order = tree.get("priority_order", [])
        for i, node_id in enumerate(priority_order):
            parts.append(f"priority_rank:{i}:{node_id}")

        # Add anomalies in sorted order
        for anomaly in sorted(anomalies):
            parts.append(f"anomaly:{anomaly}")

        # Add configuration
        parts.append(f"anomaly_threshold:{self.anomaly_threshold}")

        return "|".join(parts)
